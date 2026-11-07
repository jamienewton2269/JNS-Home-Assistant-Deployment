import base64
import hashlib
import hmac
import struct
import unittest
from club_mfa_core import (
    new_totp_secret, totp_code, verify_totp,
    create_session_handle, session_digest, privileged_session_valid,
)


class TestMFA(unittest.TestCase):
    def test_secret_has_160_bits(self):
        self.assertEqual(len(base64.b32decode(new_totp_secret() + "====")), 20)

    def test_totp_known_rfc6238_sha1_vector_truncated(self):
        secret = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(totp_code(secret, 59 // 30), "287082")
        self.assertEqual(verify_totp(secret, "287082", -1, now=59), 1)
        self.assertIsNone(verify_totp(secret, "287082", 1, now=59))

    def test_bad_code_rejected(self):
        secret = new_totp_secret()
        for value in ("12345", "1234567", "１２３４５６", "abcdef", "", None):
            self.assertIsNone(verify_totp(secret, value, -1, now=300))
        self.assertIsNone(verify_totp(secret, "000000", 11, now=300))

    def test_clock_skew_and_replay(self):
        secret = new_totp_secret()
        code = totp_code(secret, 10)
        self.assertEqual(verify_totp(secret, code, 9, now=330), 10)
        self.assertIsNone(verify_totp(secret, code, 10, now=330))
        self.assertIsNone(verify_totp(secret, code, 9, now=450))

    def test_invalid_secret_rejected(self):
        with self.assertRaises(ValueError):
            totp_code("wrong", 123)

    def test_random_opaque_handle(self):
        a, b = create_session_handle(), create_session_handle()
        self.assertNotEqual(a, b)
        self.assertEqual(session_digest(a), hashlib.sha256(a.encode()).hexdigest())

    def test_privileged_session_fail_closed(self):
        now = 1800000000
        self.assertTrue(privileged_session_valid(True, True, now - 60, now + 60, False, now))
        self.assertFalse(privileged_session_valid(False, True, now - 60, now + 60, False, now))
        self.assertFalse(privileged_session_valid(True, False, now - 60, now + 60, False, now))
        self.assertFalse(privileged_session_valid(True, True, now - 60, now + 60, True, now))
        self.assertFalse(privileged_session_valid(True, True, now - 901, now + 60, False, now))
        self.assertFalse(privileged_session_valid(True, True, now - 60, now, False, now))


if __name__ == "__main__":
    unittest.main()
