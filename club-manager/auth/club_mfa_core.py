"""Club Manager authentication primitives; NOT an HTTP authentication service.

Explicitly isolated from the existing Basic-Auth prototype. A trusted identity
provider must establish a named officer, check the enabled account state, verify
a registered credential, and persist replay counters before issuing a session.
The functions here alone never authorise database access.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time


def new_totp_secret():
    """160-bit CSPRNG secret for out-of-band authenticator enrolment."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret, counter, digits=6):
    if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
        raise ValueError("invalid counter")
    normalized = secret.strip().upper()
    if not normalized or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in normalized):
        raise ValueError("invalid base32 secret")
    key = base64.b32decode(normalized + "=" * (-len(normalized) % 8), casefold=False)
    if len(key) < 20 or digits != 6:
        raise ValueError("invalid secret length or digits")
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return f"{value % 1000000:06d}"


def verify_totp(secret, submitted_code, last_used_counter, now=None, period=30):
    """Return verified step or None; caller MUST atomically persist returned step.

    A successful code is never sufficient without a named active account,
    a credential enrolled to that account, and transactional replay exclusion.
    This helper deliberately accepts no arbitrary client-supplied timestamps.
    """
    if not isinstance(submitted_code, str) or len(submitted_code) != 6 or not submitted_code.isascii() or not submitted_code.isdecimal():
        return None
    if isinstance(last_used_counter, bool) or not isinstance(last_used_counter, int) or last_used_counter < -1:
        raise ValueError("invalid last-used counter")
    if period != 30:
        raise ValueError("unsupported TOTP period")
    current = int(time.time() if now is None else now) // period
    for counter in (current - 1, current, current + 1):
        if counter > last_used_counter and counter >= 0 and hmac.compare_digest(totp_code(secret, counter), submitted_code):
            return counter
    return None


def create_session_handle():
    """Opaque 256-bit browser bearer handle. Store its SHA-256 digest, not raw token."""
    return secrets.token_urlsafe(32)


def session_digest(handle):
    if not isinstance(handle, str) or len(handle) < 40 or len(handle) > 128:
        raise ValueError("invalid session handle")
    return hashlib.sha256(handle.encode("ascii")).hexdigest()


def privileged_session_valid(account_active, explicit_permission, verified_at, expires_at, revoked, now=None):
    """Additional application gate; database must recheck grants and session status."""
    current = time.time() if now is None else now
    return bool(account_active and explicit_permission and not revoked and
                verified_at is not None and expires_at is not None and
                verified_at <= current and current - verified_at <= 900 and expires_at > current)
