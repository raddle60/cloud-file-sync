import json
import os
import logging
from typing import Optional
from models.sync_pair import FileMeta
from core.crypto import CryptoManager, derive_key

logger = logging.getLogger(__name__)

class MetaManager:
    def __init__(self, encryption_enabled: bool, crypto: Optional[CryptoManager]):
        self.encryption_enabled = encryption_enabled
        self.crypto = crypto

    def write_meta(self, meta_path: str, meta: FileMeta) -> None:
        """写入meta文件"""
        import json
        data = meta.to_dict()
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')

        if self.encryption_enabled and self.crypto:
            content = self.crypto.encrypt_data(content)

        try:
            with open(meta_path, 'wb') as f:
                f.write(content)
        except IOError as e:
            logger.error(f"Failed to write meta file {meta_path}: {e}")
            raise

    def read_meta(self, meta_path: str) -> FileMeta:
        """读取meta文件"""
        import json
        try:
            with open(meta_path, 'rb') as f:
                content = f.read()
        except IOError as e:
            logger.error(f"Failed to read meta file {meta_path}: {e}")
            raise

        if self.encryption_enabled and self.crypto:
            try:
                content = self.crypto.decrypt_data(content)
            except Exception as e:
                logger.error(f"Failed to decrypt meta file {meta_path}: {e}")
                raise

        try:
            data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse meta file {meta_path}: {e}")
            raise

        return FileMeta.from_dict(data)
