"""RFC 6238 TOTP verification for named Club Manager officers.

NOT an authentication endpoint or session issuer. Verify the primary identity
first. The caller must atomically store the returned time-step against the
credential before accepting it; duplicate/lower steps must be rejected.
Secrets belong in encrypted protected storage, never in application logs.
"""
import base64
import binascii
import hashlib
import hmac
import struct
import time

_HASHES = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


def decode_secret(secret):
    if (not isinstance(secret, str) or not 16 <= len(secret) <= 256
            or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)):
        raise ValueError("Invalid TOTP secret")
    try:
        raw = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=False)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid TOTP secret") from None
    if len(raw) < 10:
        raise ValueError("Invalid TOTP secret")
    return raw


def hotp(secret, step, digits=6, algorithm="SHA1"):
    if not isinstance(step, int) or not 0 <= step < 2**64:
        raise ValueError("Invalid counter")
    if digits not in (6, 8) or algorithm not in _HASHES:
        raise ValueError("Invalid TOTP parameters")
    digest = hmac.new(secret, struct.pack(">Q", step), _HASHES[algorithm]).digest()
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return str(value % (10 ** digits)).zfill(digits)


def verify_totp(secret_b32, code, *, now=None, last_accepted_step=-1,
                interval=30, window=1, digits=6, algorithm="SHA1"):
    """Return matched time-step or None; caller MUST atomically consume step."""
    if not isinstance(code, str) or len(code) != digits or not code.isascii() or not code.isdecimal():
        return None
    if (not isinstance(last_accepted_step, int) or interval != 30
            or window not in (0, 1)):
        raise ValueError("Invalid TOTP parameters")
    secret = decode_secret(secret_b32)
    clock = time.time() if now is None else now
    if clock < 0:
        raise ValueError("Invalid time")
    current = int(clock // interval)
    matched = None
    for step in range(max(0, current-window), current+window+1):
        if hmac.compare_digest(hotp(secret, step, digits, algorithm), code) and step > last_accepted_step:
            matched = step
    return matched
