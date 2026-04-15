import pytest
import tempfile
import os
from cloud_file_sync.core.crypto import CryptoManager, derive_key

def test_encrypt_decrypt_small_file():
    key = derive_key("test-key-32-bytes-base64==")
    crypto = CryptoManager(key)

    original_data = b"Hello, World!"
    with tempfile.NamedTemporaryFile(delete=False) as f:
        original_path = f.name
        f.write(original_data)

    encrypted_path = original_path + ".enc"
    decrypted_path = original_path + ".dec"

    try:
        crypto.encrypt_file(original_path, encrypted_path)
        assert os.path.exists(encrypted_path)
        assert os.path.getsize(encrypted_path) != len(original_data)

        crypto.decrypt_file(encrypted_path, decrypted_path)
        with open(decrypted_path, 'rb') as f:
            decrypted_data = f.read()
        assert decrypted_data == original_data
    finally:
        for p in [original_path, encrypted_path, decrypted_path]:
            if os.path.exists(p):
                os.unlink(p)

def test_encrypt_decrypt_with_watchdog_file():
    key = derive_key("test-key-32-bytes-base64==")
    crypto = CryptoManager(key)

    original_data = b"Test content for file"
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(original_data)
        original_path = f.name

    encrypted_path = original_path + ".enc"
    decrypted_path = original_path + ".dec"

    try:
        crypto.encrypt_file(original_path, encrypted_path)
        crypto.decrypt_file(encrypted_path, decrypted_path)

        with open(decrypted_path, 'rb') as f:
            assert f.read() == original_data
    finally:
        for p in [original_path, encrypted_path, decrypted_path]:
            if os.path.exists(p):
                os.unlink(p)

def test_derive_key():
    key1 = derive_key("password123")
    key2 = derive_key("password123")
    assert key1 == key2
    assert len(key1) == 32