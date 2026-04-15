import os
import time
import hashlib
import shutil
from typing import Optional, Tuple
from cloud_file_sync.models.sync_pair import SyncPair, FileMeta
from cloud_file_sync.storage.sync_state import SyncState
from cloud_file_sync.core.crypto import CryptoManager, derive_key
from cloud_file_sync.core.conflict_resolver import ConflictResolver
from cloud_file_sync.meta.meta_manager import MetaManager
from cloud_file_sync.cloud.base import CloudStorage

class SyncEngine:
    def __init__(
        self,
        sync_pair: SyncPair,
        state: SyncState,
        cloud_storage: CloudStorage,
        crypto: Optional[CryptoManager],
        config_key: str
    ):
        self.sync_pair = sync_pair
        self.state = state
        self.cloud_storage = cloud_storage
        self.crypto = crypto
        self.config_key = config_key
        self.conflict_resolver = ConflictResolver()
        self.meta_manager = MetaManager(
            encryption_enabled=sync_pair.encryption_enabled,
            crypto=crypto
        )

    def get_cloud_name(self, filename: str) -> str:
        """生成云端文件名"""
        if self.sync_pair.encryption_enabled:
            return f"sha256({filename})"
        return filename

    def get_cloud_path(self, relative_path: str) -> str:
        """获取云端完整路径"""
        remote = self.sync_pair.remote.rstrip('/')
        rel = relative_path.lstrip('/')
        if rel:
            return f"{remote}/{rel}"
        return remote

    def get_local_path(self, relative_path: str) -> str:
        """获取本地完整路径"""
        local = self.sync_pair.local.rstrip(os.sep)
        rel = relative_path.lstrip(os.sep)
        if rel:
            return os.path.join(local, rel)
        return local

    def scan_local_files(self):
        """扫描本地文件"""
        if not os.path.exists(self.sync_pair.local):
            return

        for dirpath, dirnames, filenames in os.walk(self.sync_pair.local):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                relative_path = os.path.relpath(full_path, self.sync_pair.local)

                stat = os.stat(full_path)
                sha256 = self._calc_sha256(full_path)

                meta = FileMeta(
                    original_filename=filename,
                    size=stat.st_size,
                    last_modified=int(stat.st_mtime),
                    sha256=sha256,
                    relative_path=relative_path
                )

                cloud_name = self.get_cloud_name(filename)
                self.state.add_file(
                    self.sync_pair.local,
                    self.sync_pair.remote,
                    meta,
                    cloud_name
                )

    def _calc_sha256(self, file_path: str) -> str:
        """计算文件SHA256"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def full_sync(self):
        """执行全量同步"""
        # 1. 扫描本地文件
        self.scan_local_files()

        # 2. 获取云端文件列表
        cloud_files = self.cloud_storage.list_files(self.sync_pair.remote)

        # 3. 下载云端meta文件并对比
        # TODO: 实现详细的同步逻辑

    def atomic_upload(self, local_path: str, cloud_path: str, cloud_name: str):
        """原子上传文件到云端"""
        tmp_name = f"{cloud_name}.tmp"
        tmp_path = cloud_path + ".tmp"

        # 1. 上传到tmp
        self.cloud_storage.upload_file(local_path, tmp_path)

        # 2. 验证（优先hash，其次大小）
        try:
            cloud_hash = self.cloud_storage.get_file_hash(tmp_path)
            local_hash = self._calc_sha256(local_path)
            verified = (cloud_hash == local_hash)
        except NotImplementedError:
            cloud_size = self.cloud_storage.get_file_size(tmp_path)
            local_size = os.path.getsize(local_path)
            verified = (cloud_size == local_size)

        # 3. 原子替换
        if verified:
            self.cloud_storage.delete_file(cloud_path)
            self.cloud_storage.rename_file(tmp_path, cloud_path)
        else:
            self.cloud_storage.delete_file(tmp_path)
            raise ValueError(f"Upload verification failed for {cloud_path}")

    def atomic_download(self, cloud_path: str, local_path: str, expected_sha256: str):
        """原子下载文件到本地"""
        tmp_path = local_path + ".tmp"

        # 1. 下载到tmp
        self.cloud_storage.download_file(cloud_path, tmp_path)

        # 2. 验证hash
        if self.sync_pair.encryption_enabled and self.crypto:
            # 解密后再验证
            decrypted_tmp = tmp_path + ".dec"
            self.crypto.decrypt_file(tmp_path, decrypted_tmp)
            sha256 = self._calc_sha256(decrypted_tmp)
            os.unlink(decrypted_tmp)
        else:
            sha256 = self._calc_sha256(tmp_path)

        # 3. 原子替换
        if sha256 == expected_sha256:
            if os.path.exists(local_path):
                os.unlink(local_path)
            os.rename(tmp_path, local_path)
        else:
            os.unlink(tmp_path)
            raise ValueError(f"Download verification failed for {local_path}")
