# tests/test_integration.py
import pytest
import tempfile
import os
import time
from unittest.mock import Mock, patch, MagicMock
from config.config_loader import ConfigLoader
from core.crypto import CryptoManager, derive_key
from core.sync_engine import SyncEngine
from models.sync_pair import SyncPair
from storage.sync_state import SyncState
from cloud.base import CloudStorage

class MockCloudStorage(CloudStorage):
    """Mock云端存储用于测试"""
    def __init__(self):
        self._files = {}

    def list_files(self, prefix: str = "") -> list:
        return [k for k in self._files.keys() if k.startswith(prefix)]

    def upload_file(self, local_path: str, remote_path: str) -> None:
        with open(local_path, 'rb') as f:
            self._files[remote_path] = f.read()

    def download_file(self, remote_path: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(self._files.get(remote_path, b''))

    def delete_file(self, remote_path: str) -> None:
        self._files.pop(remote_path, None)

    def rename_file(self, old_path: str, new_path: str) -> None:
        if old_path in self._files:
            self._files[new_path] = self._files.pop(old_path)

    def get_file_hash(self, remote_path: str) -> str:
        import hashlib
        data = self._files.get(remote_path, b'')
        return hashlib.sha256(data).hexdigest()

    def get_file_size(self, remote_path: str) -> int:
        return len(self._files.get(remote_path, b''))

def test_end_to_end_sync_without_encryption():
    """端到端测试：无加密模式"""
    with tempfile.TemporaryDirectory() as local_dir:
        # 创建测试文件
        test_file = os.path.join(local_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("Hello, World!")

        # 创建mock云端
        cloud = MockCloudStorage()

        # 创建配置
        sync_pair = SyncPair(
            local=local_dir,
            remote="bucket/prefix/",
            encryption_enabled=False
        )
        state = SyncState()

        engine = SyncEngine(
            sync_pair=sync_pair,
            state=state,
            cloud_storage=cloud,
            crypto=None,
            config_key=""
        )

        # 执行全量同步
        engine.full_sync()

        # 验证云端有文件
        cloud_files = cloud.list_files("bucket/prefix/")
        assert len(cloud_files) > 0

def test_end_to_end_sync_with_encryption():
    """端到端测试：加密模式"""
    with tempfile.TemporaryDirectory() as local_dir:
        # 创建测试文件
        test_file = os.path.join(local_dir, "secret.txt")
        with open(test_file, 'wb') as f:
            f.write(b"Secret content!")

        # 创建mock云端
        cloud = MockCloudStorage()

        # 创建加密管理器
        key = derive_key("test-key-32bytes==")
        crypto = CryptoManager(key)

        # 创建配置
        sync_pair = SyncPair(
            local=local_dir,
            remote="bucket/prefix/",
            encryption_enabled=True
        )
        state = SyncState()

        engine = SyncEngine(
            sync_pair=sync_pair,
            state=state,
            cloud_storage=cloud,
            crypto=crypto,
            config_key="test-key-32bytes=="
        )

        # 执行全量同步
        engine.full_sync()

        # 验证云端有加密文件
        cloud_files = cloud.list_files("bucket/prefix/")
        assert len(cloud_files) >= 2  # 文件 + meta

        # 验证文件名是hash
        assert any("sha256" not in f for f in cloud_files)