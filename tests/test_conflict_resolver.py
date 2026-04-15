import pytest
import tempfile
import time
import os
from cloud_file_sync.core.conflict_resolver import ConflictResolver
from cloud_file_sync.models.sync_pair import FileMeta

def test_generate_conflict_name():
    resolver = ConflictResolver()

    name = resolver.generate_conflict_name("report.pdf", int(time.time()))
    assert "report" in name
    assert ".conflict-" in name
    assert name.endswith(".pdf")

def test_generate_conflict_name_no_extension():
    resolver = ConflictResolver()

    name = resolver.generate_conflict_name("README", int(time.time()))
    assert ".conflict-" in name
    assert name.startswith("README")

def test_resolve_local_conflict():
    resolver = ConflictResolver()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("original")

        new_name = resolver.resolve_local_conflict(test_file)

        assert new_name != test_file
        assert os.path.exists(new_name)
        assert not os.path.exists(test_file)

        with open(new_name, 'r') as f:
            assert f.read() == "original"

def test_conflict_decision_newer_wins():
    """测试时间戳判断新旧"""
    resolver = ConflictResolver()

    local_meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=1000,
        sha256="local123"
    )

    cloud_meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=2000,  # 云端更新
        sha256="cloud123"
    )

    winner = resolver.decide_winner(local_meta, cloud_meta)
    assert winner == "cloud"  # 云端更新，应该保留云端

def test_conflict_decision_local_newer_wins():
    """测试本地文件更新更新的情况"""
    resolver = ConflictResolver()

    local_meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=3000,  # 本地更新
        sha256="local123"
    )

    cloud_meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=2000,  # 云端旧
        sha256="cloud123"
    )

    winner = resolver.decide_winner(local_meta, cloud_meta)
    assert winner == "local"  # 本地更新，应该保留本地

def test_conflict_decision_sha256_tiebreaker():
    """测试时间戳相同，按sha256判断"""
    resolver = ConflictResolver()

    local_meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=1000,
        sha256="zzzzzzz"  # sha256更大
    )

    cloud_meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=1000,  # 时间戳相同
        sha256="aaaaaaa"
    )

    winner = resolver.decide_winner(local_meta, cloud_meta)
    assert winner == "local"  # sha256更大，保留本地

def test_handle_conflict_local_wins():
    """测试冲突处理：本地更新，云端需要重命名"""
    resolver = ConflictResolver()

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = os.path.join(tmpdir, "test.txt")
        with open(local_path, 'w') as f:
            f.write("local content")

        local_meta = FileMeta(
            original_filename="test.txt",
            size=100,
            last_modified=3000,  # 本地更新
            sha256="local123"
        )

        cloud_meta = FileMeta(
            original_filename="test.txt",
            size=100,
            last_modified=2000,
            sha256="cloud123"
        )

        local_conflict_name, cloud_conflict_name = resolver.handle_conflict(
            local_path, "test.txt", local_meta, cloud_meta
        )

        assert local_conflict_name is None
        assert cloud_conflict_name is not None
        assert ".conflict-" in cloud_conflict_name

def test_handle_conflict_cloud_wins():
    """测试冲突处理：云端更新，本地需要重命名"""
    resolver = ConflictResolver()

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = os.path.join(tmpdir, "test.txt")
        with open(local_path, 'w') as f:
            f.write("local content")

        local_meta = FileMeta(
            original_filename="test.txt",
            size=100,
            last_modified=1000,
            sha256="local123"
        )

        cloud_meta = FileMeta(
            original_filename="test.txt",
            size=100,
            last_modified=2000,  # 云端更新
            sha256="cloud123"
        )

        local_conflict_name, cloud_conflict_name = resolver.handle_conflict(
            local_path, "test.txt", local_meta, cloud_meta
        )

        assert cloud_conflict_name is None
        assert local_conflict_name is not None
        assert ".conflict-" in local_conflict_name
        assert os.path.exists(local_conflict_name)
        assert not os.path.exists(local_path)