import pytest
import tempfile
import json
import os
from meta.meta_manager import MetaManager
from models.sync_pair import FileMeta
from core.crypto import CryptoManager, derive_key

def test_meta_to_dict():
    meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=1713187200,
        sha256="abc123"
    )
    d = meta.to_dict()
    assert d["original_filename"] == "test.txt"
    assert d["size"] == 100
    assert d["last_modified"] == 1713187200
    assert d["sha256"] == "abc123"

def test_meta_from_dict():
    data = {
        "original_filename": "test.txt",
        "size": 100,
        "last_modified": 1713187200,
        "sha256": "abc123"
    }
    meta = FileMeta.from_dict(data)
    assert meta.original_filename == "test.txt"
    assert meta.size == 100

def test_meta_manager_no_encryption():
    """非加密模式meta文件读写"""
    manager = MetaManager(encryption_enabled=False, crypto=None)

    meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=1713187200,
        sha256="abc123"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        meta_path = os.path.join(tmpdir, "test.txt.meta.json")
        manager.write_meta(meta_path, meta)

        assert os.path.exists(meta_path)

        with open(meta_path, 'r') as f:
            raw = json.load(f)
        assert raw["original_filename"] == "test.txt"

        loaded = manager.read_meta(meta_path)
        assert loaded.original_filename == "test.txt"
        assert loaded.sha256 == "abc123"

def test_meta_manager_with_encryption():
    """加密模式meta文件读写"""
    key = derive_key("test-key")
    crypto = CryptoManager(key)
    manager = MetaManager(encryption_enabled=True, crypto=crypto)

    meta = FileMeta(
        original_filename="test.txt",
        size=100,
        last_modified=1713187200,
        sha256="abc123"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        meta_path = os.path.join(tmpdir, "test.txt.meta.json")
        manager.write_meta(meta_path, meta)

        assert os.path.exists(meta_path)

        # 加密后不应是明文JSON
        with open(meta_path, 'rb') as f:
            raw = f.read()
        assert b'{"original_filename"' not in raw

        loaded = manager.read_meta(meta_path)
        assert loaded.original_filename == "test.txt"
        assert loaded.sha256 == "abc123"
