"""WebAuthn ceremony engine. No HTTP routes or production enrollment are enabled.

Requires py_webauthn 3.0.1. Enrolment is permitted only when the injected
trusted Store validates independent approval. No public self-registration.
The Store MUST persist and atomically consume one-time challenges, verify
officer state and commit credential counters in a transaction.
"""
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID
import hashlib

from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
)


@dataclass(frozen=True)
class Credential:
    id: bytes
    public_key: bytes
    sign_count: int


class WebAuthnFlow:
    def __init__(self, rp_id: str, origin: str, store):
        parsed = urlsplit(origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.hostname != rp_id
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.username or parsed.password):
            raise ValueError("An exact HTTPS relying-party origin and matching RP ID are required")
        self.rp_id, self.origin, self.store = rp_id, origin.rstrip("/"), store

    def begin_enrolment(self, account_id: UUID, name: str, display_name: str):
        # This checks a durable two-officer/recovery or eligible invitation grant.
        # Merely knowing the account ID cannot authorize credential enrollment.
        if not self.store.enrolment_approved(account_id):
            raise PermissionError("Officer enrolment is not authorised")
        existing = self.store.credentials_for(account_id)
        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name="Club Manager",
            user_id=account_id.bytes,
            user_name=name,
            user_display_name=display_name,
            exclude_credentials=[PublicKeyCredentialDescriptor(id=c.id) for c in existing],
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        self.store.save_challenge(account_id, "register", hashlib.sha256(options.challenge).digest(), options.challenge)
        return options_to_json(options)

    def finish_enrolment(self, account_id: UUID, challenge_id: UUID, response: dict):
        # The store must atomically consume the challenge BEFORE crypto checks;
        # any failed verification still burns it to prevent replays.
        challenge = self.store.claim_challenge(challenge_id, account_id, "register")
        if challenge is None or not self.store.enrolment_approved(account_id):
            raise PermissionError("Invalid or unapproved WebAuthn enrolment")
        result = verify_registration_response(
            credential=response,
            expected_challenge=challenge,
            expected_rp_id=self.rp_id,
            expected_origin=self.origin,
            require_user_verification=True,
        )
        cred = Credential(result.credential_id, result.credential_public_key, result.sign_count)
        self.store.add_credential(account_id, cred)  # unique credential ID enforced in DB
        return cred

    def begin_login(self, account_id: UUID):
        if not self.store.officer_active(account_id):
            raise PermissionError("Account unavailable")
        credentials = self.store.credentials_for(account_id)
        if not credentials:
            raise PermissionError("No verified security key enrolled")
        options = generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=[PublicKeyCredentialDescriptor(id=c.id) for c in credentials],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        self.store.save_challenge(account_id, "authenticate", hashlib.sha256(options.challenge).digest(), options.challenge)
        return options_to_json(options)

    def finish_login(self, account_id: UUID, challenge_id: UUID, response: dict):
        challenge = self.store.claim_challenge(challenge_id, account_id, "authenticate")
        if challenge is None or not self.store.officer_active(account_id):
            raise PermissionError("Invalid WebAuthn challenge or inactive account")
        # The claimed credential ID is untrusted until the signature is verified.
        from webauthn import base64url_to_bytes
        claimed_id = base64url_to_bytes(response.get("id", ""))
        cred = next((c for c in self.store.credentials_for(account_id) if c.id == claimed_id), None)
        if cred is None:
            raise PermissionError("Credential not registered to the officer")
        result = verify_authentication_response(
            credential=response,
            expected_challenge=challenge,
            expected_rp_id=self.rp_id,
            expected_origin=self.origin,
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
            require_user_verification=True,
        )
        # Commit only AFTER real signature/origin/RP/UV validation. This must be
        # atomic, and rejects smaller nonzero counters or revoked credentials.
        if not self.store.commit_counter(account_id, cred.id, result.new_sign_count):
            raise PermissionError("Credential was revoked or its counter regressed")
        return account_id  # Not an API session; session broker remains separate.
