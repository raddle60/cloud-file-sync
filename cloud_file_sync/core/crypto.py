import os
import hashlib
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def derive_key(password: str) -> bytes:
    """从密码派生32字节密钥"""
    return hashlib.sha256(password.encode()).digest()

class CryptoManager:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("Key must be 32 bytes")
        self.key = key
        self.aesgcm = AESGCM(key)

    def encrypt_data(self, data: bytes) -> bytes:
        """加密数据，返回 IV + 密文 + auth_tag"""
        iv = os.urandom(16)
        ciphertext = self.aesgcm.encrypt(iv, data, None)
        return iv + ciphertext

    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """解密数据"""
        iv = encrypted_data[:16]
        ciphertext = encrypted_data[16:]
        return self.aesgcm.decrypt(iv, ciphertext, None)

    def encrypt_file(self, input_path: str, output_path: str) -> None:
        """加密文件"""
        with open(input_path, 'rb') as f:
            data = f.read()
        encrypted = self.encrypt_data(data)
        with open(output_path, 'wb') as f:
            f.write(encrypted)

    def decrypt_file(self, input_path: str, output_path: str) -> None:
        """解密文件"""
        with open(input_path, 'rb') as f:
            encrypted_data = f.read()
        decrypted = self.decrypt_data(encrypted_data)
        with open(output_path, 'wb') as f:
            f.write(decrypted)

    def hash_file(self, file_path: str) -> str:
        """计算文件SHA256哈希"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()