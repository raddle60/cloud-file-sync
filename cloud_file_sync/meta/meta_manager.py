import json
import os
from typing import Optional
from cloud_file_sync.models.sync_pair import FileMeta
from cloud_file_sync.core.crypto import CryptoManager, derive_key

class MetaManager:
    def __init__(self, encryption_enabled: bool, crypto: Optional[CryptoManager]):
        self.encryption_enabled = encryption_enabled
        self.crypto = crypto

    def write_meta(self, meta_path: str, meta: FileMeta) -> None:
        """写入meta文件"""
        data = meta.to_dict()
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')

        if self.encryption_enabled and self.crypto:
            content = self.crypto.encrypt_data(content)

        with open(meta_path, 'wb') as f:
            f.write(content)

    def read_meta(self, meta_path: str) -> FileMeta:
        """读取meta文件"""
        with open(meta_path, 'rb') as f:
            content = f.read()

        if self.encryption_enabled and self.crypto:
            content = self.crypto.decrypt_data(content)

        data = json.loads(content.decode('utf-8'))
        return FileMeta.from_dict(data)
