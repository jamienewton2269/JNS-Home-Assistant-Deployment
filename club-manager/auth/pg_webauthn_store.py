"""PostgreSQL bridge for the upstream py_webauthn ceremony engine.

No HTTP listener, account bootstrap or enrolment route. The connection factory
MUST authenticate as a distinct, constrained verification service that has the
NOLOGIN club_authn_service role explicitly granted by a future reviewed deploy.

Every ceremony call runs in its own transaction, so a failed cryptographic
verification cannot roll back consumption of the one-time challenge.
"""
from contextlib import closing
from dataclasses import dataclass
from uuid import UUID

from webauthn_flow import Credential


class PostgreSQLWebAuthnStore:
    def __init__(self, connection_factory):
        self.connect = connection_factory

    def _one(self, sql, args):
        with closing(self.connect()) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, args)
                    row = cur.fetchone()
                    return None if row is None else row[0]

    def officer_active(self, account_id: UUID):
        return bool(self._one(
            "SELECT club.active_officer_for_authn(%s)", (account_id,)))

    def enrolment_approved(self, account_id: UUID):
        # An initial invite cannot self-activate. Existing officers can recover
        # credentials only with two fresh independent MFA-backed approvals.
        return bool(self._one("""
          SELECT EXISTS (
            SELECT 1 FROM club.security_change_requests r
             WHERE r.subject_account_id=%s
               AND r.change_kind='account_recovery'
               AND r.status='pending'
               AND r.expires_at>clock_timestamp()
               AND club.security_change_ready(r.id)
          ) AND club.active_officer_for_authn(%s)
        """, (account_id, account_id)))

    def credentials_for(self, account_id: UUID):
        with closing(self.connect()) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                      SELECT credential_id,public_key,signature_counter
                        FROM club.verified_officer_webauthn_credentials(%s)
                    """, (account_id,))
                    return [Credential(bytes(id_), bytes(key), count)
                            for id_, key, count in cur.fetchall()]

    def save_challenge(self, account_id: UUID, purpose: str, digest: bytes, challenge: bytes):
        # Digest is checked by the DB on consumption; don't accept an incorrect
        # caller-supplied digest or a weak/short challenge.
        import hashlib
        if hashlib.sha256(challenge).digest() != digest or len(challenge) < 32:
            raise ValueError("Invalid challenge")
        return self._one(
            "SELECT club.start_webauthn_challenge(%s,%s,%s)",
            (account_id, purpose, challenge))

    def claim_challenge(self, challenge_id: UUID, account_id: UUID, purpose: str):
        value = self._one(
            "SELECT club.claim_webauthn_challenge(%s,%s,%s)",
            (challenge_id, account_id, purpose))
        return bytes(value) if value is not None else None

    def add_credential(self, account_id: UUID, credential: Credential):
        if not self.enrolment_approved(account_id):
            raise PermissionError("Independent approval required")
        ok = self._one("""
            SELECT club.register_verified_webauthn_credential(%s,%s,%s,%s)
        """, (account_id, credential.id, credential.public_key, credential.sign_count))
        if not ok:
            raise PermissionError("Unable to register credential")

    def commit_counter(self, account_id: UUID, credential_id: bytes, counter: int):
        return bool(self._one(
            "SELECT club.commit_webauthn_counter(%s,%s,%s)",
            (account_id, credential_id, counter)))
