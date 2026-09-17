import unittest
from veda.security import encrypt_secret, decrypt_secret, mask_key

class TestSecurity(unittest.TestCase):
    def test_dpapi_roundtrip(self):
        secret = "sk-test-secret-key-abcdef-12345"
        enc = encrypt_secret(secret)
        self.assertNotEqual(secret, enc)
        dec = decrypt_secret(enc)
        self.assertEqual(secret, dec)

    def test_empty_secret(self):
        self.assertEqual(encrypt_secret(""), "")
        self.assertEqual(decrypt_secret(""), "")

    def test_mask_key(self):
        self.assertEqual(mask_key(""), "(Not Set)")
        self.assertEqual(mask_key(None), "(Not Set)")
        self.assertEqual(mask_key("123456"), "••••56")
        self.assertEqual(mask_key("sk-abcdefgh1234"), "••••••••1234")

if __name__ == '__main__':
    unittest.main()
