"""Small integration controller for a PRIVATE Club Manager WebAuthn beta.

No listener and no automatic bootstrap. Uses existing upstream WebAuthn flow,
existing PostgreSQL roles and stdlib cookies. A separate reviewed HTTP handler
must call complete_passkey() ONLY after a trusted ceremony and approved enrolment.
"""
from contextlib import closing
from http.cookies import SimpleCookie
import hashlib
import secrets

from webauthn import base64url_to_bytes

COOKIE_NAME = "__Host-club_session"
COOKIE_MAX_AGE_SECONDS = 900


class OfficerController:
    def __init__(self, webauthn_flow, authn_db_factory, read_api):
        self.flow = webauthn_flow
        self.authn_db_factory = authn_db_factory
        self.read_api = read_api

    def begin_passkey(self, officer_id):
        return self.flow.begin_login(officer_id)

    def complete_passkey(self, officer_id, challenge_id, response):
        # The upstream library validates the actual assertion including
        # challenge, RP, origin, user verification and cryptographic signature.
        verified_officer = self.flow.finish_login(officer_id, challenge_id, response)
        if verified_officer != officer_id:
            raise PermissionError("WebAuthn identity mismatch")
        verified_credential_id = base64url_to_bytes(response["id"])
        token = secrets.token_urlsafe(48)
        digest = hashlib.sha256(token.encode("ascii")).digest()
        with closing(self.authn_db_factory()) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT club.complete_verified_webauthn_login(%s,%s,%s)",
                        (verified_officer, verified_credential_id, digest))
                    row = cur.fetchone()
                    if not row or row[0] is None:
                        raise PermissionError("No verified officer session issued")
        return self._secure_cookie(token)

    @staticmethod
    def _secure_cookie(token):
        cookie = SimpleCookie()
        cookie[COOKIE_NAME] = token
        cookie[COOKIE_NAME]["path"] = "/"
        cookie[COOKIE_NAME]["secure"] = True
        cookie[COOKIE_NAME]["httponly"] = True
        cookie[COOKIE_NAME]["samesite"] = "Strict"
        cookie[COOKIE_NAME]["max-age"] = COOKIE_MAX_AGE_SECONDS
        return cookie[COOKIE_NAME].OutputString()

    @staticmethod
    def clear_cookie():
        cookie = SimpleCookie()
        cookie[COOKIE_NAME] = ""
        cookie[COOKIE_NAME]["path"] = "/"
        cookie[COOKIE_NAME]["secure"] = True
        cookie[COOKIE_NAME]["httponly"] = True
        cookie[COOKIE_NAME]["samesite"] = "Strict"
        cookie[COOKIE_NAME]["max-age"] = 0
        return cookie[COOKIE_NAME].OutputString()

    def read(self, route, cookie_header):
        if not isinstance(cookie_header, str) or len(cookie_header) > 4096:
            raise PermissionError("Invalid session cookie")
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except Exception:
            raise PermissionError("Invalid session cookie") from None
        item = cookie.get(COOKIE_NAME)
        if item is None:
            raise PermissionError("Named officer session required")
        return self.read_api.get(route, item.value)
