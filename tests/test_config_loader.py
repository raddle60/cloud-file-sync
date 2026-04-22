import pytest
import json
import tempfile
import os
from config.config_loader import ConfigLoader, Config
from models.sync_pair import SyncPair, CloudType
from utils.path_util import PathUtil

def test_load_config_success():
    temp_dir = tempfile.gettempdir()
    config_data = {
        "encryption_enabled": True,
        "encryption_key": "dGVzdC1rZXktMzItYnl0ZXMtYmFzZTY0",
        "sync_pairs": [
            {"local": temp_dir, "remote": "bucket/prefix/"}
        ]
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    try:
        loader = ConfigLoader(temp_path)
        config = loader.load()
        assert config.encryption_enabled == True
        assert len(config.sync_pairs) == 1
        assert PathUtil.normalize_path(config.sync_pairs[0].local) == PathUtil.normalize_path(temp_dir)
    finally:
        os.unlink(temp_path)

def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        ConfigLoader("/nonexistent/config.json").load()

def test_load_config_invalid_json():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("not valid json")
        temp_path = f.name
    try:
        with pytest.raises(json.JSONDecodeError):
            ConfigLoader(temp_path).load()
    finally:
        os.unlink(temp_path)

def test_config_cloud_type():
    config_data = {
        "cloud_type": "local_mock",
        "encryption_enabled": False,
        "encryption_key": "key",
        "sync_pairs": []
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    try:
        loader = ConfigLoader(temp_path)
        config = loader.load()
        assert config.cloud_type == CloudType.LOCAL_MOCK
    finally:
        os.unlink(temp_path)

def test_config_remote_path_conflict():
    """测试 remote 路径冲突检测"""
    config_data = {
        "cloud_type": "local_mock",
        "encryption_enabled": False,
        "encryption_key": "key",
        "sync_pairs": [
            {"local": "/local1", "remote": "bucket/prefix1/"},
            {"local": "/local2", "remote": "bucket/prefix1/subdir/"}
        ]
    }
    config = Config.from_dict(config_data)
    with pytest.raises(ValueError, match="Remote path conflict"):
        config.validate_remote_paths()

def test_config_remote_path_no_conflict():
    """测试 remote 路径无冲突"""
    config_data = {
        "cloud_type": "local_mock",
        "encryption_enabled": False,
        "encryption_key": "key",
        "sync_pairs": [
            {"local": "/local1", "remote": "bucket/prefix1/"},
            {"local": "/local2", "remote": "bucket/prefix2/"}
        ]
    }
    config = Config.from_dict(config_data)
    config.validate_remote_paths()  # Should not raise