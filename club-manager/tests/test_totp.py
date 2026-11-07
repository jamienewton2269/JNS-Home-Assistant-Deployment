import base64
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "auth" / "totp.py"
spec = importlib.util.spec_from_file_location("club_totp", path)
totp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(totp)


class TotpTests(unittest.TestCase):
    def setUp(self):
        self.raw = b"12345678901234567890"
        self.encoded = base64.b32encode(self.raw).decode().rstrip("=")

    def test_rfc6238_sha1_8_digits(self):
        self.assertEqual(totp.hotp(self.raw, 1, 8), "94287082")
        self.assertEqual(totp.verify_totp(self.encoded, "94287082", now=59, digits=8), 1)

    def test_six_digit_fallback(self):
        self.assertEqual(totp.hotp(self.raw, 1), "287082")
        self.assertEqual(totp.verify_totp(self.encoded, "287082", now=59), 1)

    def test_replay_cannot_reuse_step(self):
        self.assertIsNone(totp.verify_totp(self.encoded, "287082", now=59, last_accepted_step=1))
        self.assertIsNone(totp.verify_totp(self.encoded, "287082", now=59, last_accepted_step=2))

    def test_bad_code_rejected(self):
        for bad in ("", "00000", "0000000", "abcdef", "１２３４５６", "12 345"):
            self.assertIsNone(totp.verify_totp(self.encoded, bad, now=59))

    def test_expired_window(self):
        self.assertIsNone(totp.verify_totp(self.encoded, "287082", now=180))

    def test_window_policy(self):
        self.assertIsNone(totp.verify_totp(self.encoded, "287082", now=90, window=1))
        self.assertEqual(totp.verify_totp(self.encoded, "287082", now=61, window=1), 1)
        self.assertIsNone(totp.verify_totp(self.encoded, "287082", now=61, window=0))

    def test_broken_secret_rejected(self):
        for bad in ("not-base32", "A", "A" * 260, " " + self.encoded):
            with self.assertRaises(ValueError):
                totp.decode_secret(bad)

    def test_algorithm_validation(self):
        with self.assertRaises(ValueError):
            totp.hotp(self.raw, 1, algorithm="MD5")


if __name__ == "__main__":
    unittest.main()
