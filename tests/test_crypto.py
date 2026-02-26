from __future__ import annotations

import unittest

from core.crypto import CryptoManager, decrypt_field, encrypt_field


class CryptoTests(unittest.TestCase):
    def test_encrypt_decrypt_field(self):
        data_key = CryptoManager.generate_data_key()
        plain = 'secret-value-123'
        enc = encrypt_field(plain, data_key)
        self.assertNotEqual(enc.decode('utf-8'), plain)
        dec = decrypt_field(enc, data_key)
        self.assertEqual(dec, plain)


if __name__ == '__main__':
    unittest.main()
