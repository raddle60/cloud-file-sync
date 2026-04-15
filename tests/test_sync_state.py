# tests/test_sync_state.py
import pytest
import tempfile
import time
from cloud_file_sync.storage.sync_state import SyncState
from cloud_file_sync.models.sync_pair import FileMeta, SyncPair

def test_sync_state_add_file():
    state = SyncState()

    meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=int(time.time()),
        sha256="abc123",
        relative_path="subdir/test.txt"
    )

    state.add_file("/local/root", "bucket/prefix/", meta, "sha256(original_filename)")

    assert state.has_local_file("/local/root", "subdir/test.txt")
    assert state.has_cloud_meta("bucket/prefix/", "sha256(original_filename)")

def test_sync_state_remove_local_file():
    state = SyncState()

    meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=int(time.time()),
        sha256="abc123",
        relative_path="test.txt"
    )

    state.add_file("/local/root", "bucket/prefix/", meta, "hash")

    # 模拟本地文件被删除
    state.mark_local_deleted("/local/root", "test.txt", int(time.time()))

    assert not state.has_local_file("/local/root", "test.txt")
    info = state.get_local_file_info("/local/root", "test.txt")
    assert info is not None
    assert info.get("deleted") == True

def test_sync_state_get_cloud_meta():
    state = SyncState()

    meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=int(time.time()),
        sha256="abc123",
        relative_path="test.txt"
    )

    state.add_file("/local/root", "bucket/prefix/", meta, "hash")

    cloud_meta = state.get_cloud_meta("bucket/prefix/", "hash")
    assert cloud_meta is not None
    assert cloud_meta.sha256 == "abc123"

def test_sync_state_get_files_needing_sync():
    state = SyncState()

    # 添加一个本地文件（云端没有）
    meta = FileMeta(
        original_filename="new.txt",
        size=100,
        last_modified=int(time.time()),
        sha256="new123",
        relative_path="new.txt"
    )
    state.add_file("/local/root", "bucket/prefix/", meta, "hash_new")

    to_sync = state.get_files_needing_sync("/local/root", "bucket/prefix/")
    assert len(to_sync) > 0