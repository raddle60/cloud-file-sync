import pytest
import tempfile
import time
import os
import hashlib
from unittest.mock import Mock, patch, MagicMock
from core.sync_engine import SyncEngine
from models.sync_pair import SyncPair, FileMeta
from storage.sync_state import SyncState

@pytest.fixture
def temp_dirs():
    with tempfile.TemporaryDirectory() as local_dir:
        with tempfile.TemporaryDirectory() as cloud_dir:
            yield local_dir, cloud_dir

def test_sync_engine_init():
    sync_pair = SyncPair(
        local="/tmp/local",
        remote="bucket/prefix/",
        encryption_enabled=False
    )
    state = SyncState()
    engine = SyncEngine(sync_pair, state, None, None, None)
    assert engine.sync_pair == sync_pair
    assert engine.state == state

def test_cloud_name_generation_encrypted():
    """测试加密模式云端文件名生成"""
    sync_pair = SyncPair(
        local="/tmp/local",
        remote="bucket/prefix/",
        encryption_enabled=True
    )
    state = SyncState()
    engine = SyncEngine(sync_pair, state, None, None, None)

    name = engine.get_cloud_name("test.txt")
    assert name == hashlib.sha256("test.txt".encode()).hexdigest()
    assert len(name) == 64  # sha256 hex digest is 64 characters

def test_cloud_name_generation_plain():
    """测试非加密模式云端文件名"""
    sync_pair = SyncPair(
        local="/tmp/local",
        remote="bucket/prefix/",
        encryption_enabled=False
    )
    state = SyncState()
    engine = SyncEngine(sync_pair, state, None, None, None)

    name = engine.get_cloud_name("test.txt")
    assert name == "test.txt"

def test_local_to_cloud_path():
    sync_pair = SyncPair(
        local="/tmp/local",
        remote="bucket/prefix/",
        encryption_enabled=False
    )
    state = SyncState()
    engine = SyncEngine(sync_pair, state, None, None, None)

    path = engine.get_cloud_path("subdir/test.txt")
    assert path == "bucket/prefix/subdir/test.txt"
