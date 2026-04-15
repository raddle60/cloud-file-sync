import pytest
import json
import tempfile
import os
from cloud_file_sync.config.config_loader import ConfigLoader, Config

def test_load_config_success():
    config_data = {
        "encryption_enabled": True,
        "encryption_key": "dGVzdC1rZXktMzItYnl0ZXMtYmFzZTY0",
        "sync_pairs": [
            {"local": "/tmp/test", "remote": "bucket/prefix/"}
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
        assert config.sync_pairs[0].local == "/tmp/test"
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