import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

# Mock the baidu module before importing
sys.modules['baidu'] = MagicMock()
sys.modules['baidu.bce'] = MagicMock()
sys.modules['baidu.bce.bos'] = MagicMock()
sys.modules['baidu.bce.auth'] = MagicMock()

from cloud.baidu_bos import BaiduBOS

@pytest.fixture
def mock_bos_client():
    with patch('cloud.baidu_bos.BosClient') as mock:
        yield mock

def test_baidu_bos_init(mock_bos_client):
    bos = BaiduBOS(
        access_key_id="test_id",
        access_key_secret="test_secret",
        endpoint="http://bj.bcebos.com",
        bucket_name="test-bucket"
    )
    assert bos.bucket_name == "test-bucket"

def test_list_files(mock_bos_client):
    mock_client_instance = MagicMock()
    mock_bos_client.return_value = mock_client_instance

    mock_client_instance.list_objects.return_value = {
        'contents': [
            {'key': 'file1.txt'},
            {'key': 'file2.txt'},
        ]
    }

    bos = BaiduBOS("id", "secret", "endpoint", "bucket")
    files = bos.list_files("")
    assert 'file1.txt' in files
    assert 'file2.txt' in files

def test_upload_file(mock_bos_client):
    mock_client_instance = MagicMock()
    mock_bos_client.return_value = mock_client_instance

    bos = BaiduBOS("id", "secret", "endpoint", "bucket")
    bos.upload_file("/local/path.txt", "remote/path.txt")

    mock_client_instance.put_object_from_file.assert_called_once()

def test_download_file(mock_bos_client):
    mock_client_instance = MagicMock()
    mock_bos_client.return_value = mock_client_instance

    bos = BaiduBOS("id", "secret", "endpoint", "bucket")
    bos.download_file("remote/path.txt", "/local/path.txt")

    mock_client_instance.get_object_to_file.assert_called_once()

def test_delete_file(mock_bos_client):
    mock_client_instance = MagicMock()
    mock_bos_client.return_value = mock_client_instance

    bos = BaiduBOS("id", "secret", "endpoint", "bucket")
    bos.delete_file("remote/path.txt")

    mock_client_instance.delete_object.assert_called_once_with("bucket", "remote/path.txt")

def test_rename_file(mock_bos_client):
    mock_client_instance = MagicMock()
    mock_bos_client.return_value = mock_client_instance

    bos = BaiduBOS("id", "secret", "endpoint", "bucket")
    bos.rename_file("old_path.txt", "new_path.txt")

    mock_client_instance.copy_object.assert_called_once()
    mock_client_instance.delete_object.assert_called_once()

def test_get_file_hash(mock_bos_client):
    mock_client_instance = MagicMock()
    mock_bos_client.return_value = mock_client_instance

    mock_client_instance.get_object_metadata.return_value = MagicMock(
        metadata={'x-bce-content-sha256': 'abc123hash'}
    )

    bos = BaiduBOS("id", "secret", "endpoint", "bucket")
    hash_result = bos.get_file_hash("remote/path.txt")

    assert hash_result == "abc123hash"
    mock_client_instance.get_object_metadata.assert_called_once_with("bucket", "remote/path.txt")

def test_get_file_size(mock_bos_client):
    mock_client_instance = MagicMock()
    mock_bos_client.return_value = mock_client_instance

    mock_client_instance.get_object_metadata.return_value = MagicMock(
        metadata={'Content-Length': '1024'}
    )

    bos = BaiduBOS("id", "secret", "endpoint", "bucket")
    size_result = bos.get_file_size("remote/path.txt")

    assert size_result == 1024
    mock_client_instance.get_object_metadata.assert_called_once_with("bucket", "remote/path.txt")