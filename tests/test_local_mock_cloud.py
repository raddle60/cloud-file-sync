"""
test_local_mock_cloud.py - LocalMockCloudStorage单元测试
"""
import pytest
import tempfile
import os
import time
from cloud.local_mock_cloud import LocalMockCloudStorage


@pytest.fixture
def mock_cloud():
    """创建临时Mock云存储"""
    with tempfile.TemporaryDirectory() as base_dir:
        cloud = LocalMockCloudStorage(base_dir, "")
        yield cloud
        # 清理
        cloud.cleanup()


class TestLocalMockCloudStorageBasic:
    """基本功能测试"""

    def test_init_creates_directory(self, mock_cloud):
        """测试初始化创建目录"""
        assert os.path.exists(mock_cloud.bucket_dir)
        assert mock_cloud.bucket_name == ""

    def test_upload_and_list(self, mock_cloud):
        """测试上传和列出文件"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Hello, Cloud!")
            local_path = f.name

        # 创建对应的meta文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt.meta.json') as f:
            import json
            meta_content = json.dumps({
                "original_filename": "test.txt",
                "size": 12,
                "last_modified": 1234567890,
                "sha256": "abc123"
            })
            f.write(meta_content)
            meta_local = f.name

        # 创建tmp文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt.tmp') as f:
            f.write("Hello, Cloud!")
            tmp_local_path = f.name

        try:
            # 上传主文件
            remote_path = "test.txt"
            mock_cloud.upload_file(local_path, remote_path)

            # 上传meta文件
            meta_remote_path = "test.txt.meta.json"
            mock_cloud.upload_file(meta_local, meta_remote_path)

            # 上传主文件
            tmp_remote_path = "test.txt.tmp"
            mock_cloud.upload_file(tmp_local_path, tmp_remote_path)

            # 列出文件（不含tmp）
            files = mock_cloud.list_files()
            assert len(files) == 2
            assert any("test.txt" in f for f in files)
            assert any(".meta.json" in f for f in files)


            # 使用is_include_tmp=True列出文件，应包含temp文件
            all_files = mock_cloud.list_files(is_include_tmp=True)
            assert len(all_files) == 3
            assert any("test.txt" in f for f in all_files)
            assert any("test.txt.tmp" in f for f in all_files)
            assert any(".meta.json" in f for f in all_files)
        finally:
            os.unlink(local_path)
            os.unlink(tmp_local_path)
            os.unlink(meta_local)

    def test_download_file(self, mock_cloud):
        """测试下载文件"""
        # 创建并上传文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Download test content")
            local_path = f.name

        try:
            remote_path = "download_test.txt"
            mock_cloud.upload_file(local_path, remote_path)

            # 下载到新位置
            download_path = os.path.join(tempfile.gettempdir(), "downloaded.txt")
            mock_cloud.download_file(remote_path, download_path)

            assert os.path.exists(download_path)
            with open(download_path, 'r') as f:
                assert f.read() == "Download test content"
            os.unlink(download_path)
        finally:
            os.unlink(local_path)

    def test_delete_file(self, mock_cloud):
        """测试删除文件"""
        # 创建并上传文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Delete test")
            local_path = f.name

        # 创建对应的meta文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt.meta.json') as f:
            import json
            meta_content = json.dumps({
                "original_filename": "delete_test.txt",
                "size": 11,
                "last_modified": 1234567890,
                "sha256": "def456"
            })
            f.write(meta_content)
            meta_local = f.name

        try:
            remote_path = "delete_test.txt"
            meta_remote_path = "delete_test.txt.meta.json"

            # 上传主文件和meta文件
            mock_cloud.upload_file(local_path, remote_path)
            mock_cloud.upload_file(meta_local, meta_remote_path)

            # 验证存在
            assert mock_cloud.file_exists(remote_path)
            assert mock_cloud.file_exists(meta_remote_path)

            # 删除主文件
            mock_cloud.delete_file(remote_path)

            # 验证主文件已删除
            assert not mock_cloud.file_exists(remote_path)

            # 验证meta文件仍然存在（永不删除）
            assert mock_cloud.file_exists(meta_remote_path)
        finally:
            os.unlink(local_path)
            os.unlink(meta_local)

    def test_rename_file(self, mock_cloud):
        """测试重命名文件"""
        # 创建并上传文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Rename test")
            local_path = f.name

        # 创建对应的meta文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt.meta.json') as f:
            import json
            meta_content = json.dumps({
                "original_filename": "old_name.txt",
                "size": 11,
                "last_modified": 1234567890,
                "sha256": "ghi789"
            })
            f.write(meta_content)
            meta_local = f.name

        try:
            old_path = "old_name.txt"
            new_path = "new_name.txt"
            old_meta_path = "old_name.txt.meta.json"
            new_meta_path = "new_name.txt.meta.json"

            # 上传主文件和meta文件
            mock_cloud.upload_file(local_path, old_path)
            mock_cloud.upload_file(meta_local, old_meta_path)

            # 重命名主文件
            mock_cloud.rename_file(old_path, new_path)

            # 验证新文件存在，旧文件不存在
            assert mock_cloud.file_exists(new_path)
            assert not mock_cloud.file_exists(old_path)

            # meta文件应该还在原位置（LocalMockCloudStorage不处理meta重命名）
            # 这是因为meta重命名应该由SyncEngine处理
            assert mock_cloud.file_exists(old_meta_path)
        finally:
            os.unlink(local_path)
            os.unlink(meta_local)

    def test_get_file_hash(self, mock_cloud):
        """测试获取文件hash"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Hash test content")
            local_path = f.name

        try:
            remote_path = "hash_test.txt"
            mock_cloud.upload_file(local_path, remote_path)

            # 获取hash
            hash1 = mock_cloud.get_file_hash(remote_path)
            assert len(hash1) == 64  # SHA256 hex digest

            # 再次获取应该相同
            hash2 = mock_cloud.get_file_hash(remote_path)
            assert hash1 == hash2
        finally:
            os.unlink(local_path)

    def test_get_file_size(self, mock_cloud):
        """测试获取文件大小"""
        content = "Size test content"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(content)
            local_path = f.name

        try:
            remote_path = "size_test.txt"
            mock_cloud.upload_file(local_path, remote_path)

            size = mock_cloud.get_file_size(remote_path)
            assert size == len(content.encode('utf-8'))
        finally:
            os.unlink(local_path)


class TestLocalMockCloudStorageList:
    """list_files功能测试"""

    def test_list_empty(self, mock_cloud):
        """测试列出空目录"""
        files = mock_cloud.list_files()
        assert files == []

    def test_list_with_prefix(self, mock_cloud):
        """测试带前缀的列出"""
        # 上传多个文件
        files_to_upload = [
            ("folder1/file1.txt", "content1"),
            ("folder1/file2.txt", "content2"),
            ("folder2/file3.txt", "content3"),
        ]

        for remote_path, content in files_to_upload:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
                f.write(content)
                local_path = f.name
            try:
                mock_cloud.upload_file(local_path, remote_path)
            finally:
                os.unlink(local_path)

        # 列出所有
        all_files = mock_cloud.list_files()
        assert len(all_files) == 3

        # 按前缀过滤
        folder1_files = mock_cloud.list_files("folder1/")
        assert len(folder1_files) == 2

        folder2_files = mock_cloud.list_files("folder2/")
        assert len(folder2_files) == 1

    def test_list_excludes_tmp_files(self, mock_cloud):
        """测试list_files排除tmp文件"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Normal file")
            normal_path = f.name

        try:
            remote_path = "normal.txt"
            mock_cloud.upload_file(normal_path, remote_path)

            # 手动创建一个tmp文件（模拟上传过程中的临时文件）
            tmp_local = os.path.join(mock_cloud.bucket_dir, "temp.txt.tmp")
            os.makedirs(os.path.dirname(tmp_local), exist_ok=True)
            with open(tmp_local, 'w') as f:
                f.write("temp")

            files = mock_cloud.list_files()
            # 应该不包含tmp文件
            assert all(not f.endswith('.tmp') for f in files)
        finally:
            os.unlink(normal_path)
            if os.path.exists(tmp_local):
                os.unlink(tmp_local)


class TestLocalMockCloudStorageAtomic:
    """原子操作测试（模拟SyncEngine的原子上传下载）"""

    def test_atomic_upload_simulation(self, mock_cloud):
        """模拟原子上传：先传tmp，再重命名"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Atomic upload test")
            local_path = f.name

        try:
            remote_path = "atomic.txt"
            cloud_name = "atomic.txt"
            tmp_path = remote_path + ".tmp"

            # 1. 上传到tmp
            mock_cloud.upload_file(local_path, tmp_path)
            assert mock_cloud.file_exists(tmp_path)
            assert not mock_cloud.file_exists(remote_path)

            # 2. 验证
            hash1 = mock_cloud.get_file_hash(tmp_path)
            local_hash = mock_cloud.get_file_hash(local_path)  # 使用本地文件计算hash

            # 3. 原子替换：删除旧文件，重命名tmp
            if hash1 == local_hash:  # 简化验证
                mock_cloud.delete_file(remote_path)
                mock_cloud.rename_file(tmp_path, remote_path)

            assert mock_cloud.file_exists(remote_path)
            assert not mock_cloud.file_exists(tmp_path)
        finally:
            os.unlink(local_path)


class TestLocalMockCloudStorageErrors:
    """错误处理测试"""

    def test_download_nonexistent_raises(self, mock_cloud):
        """测试下载不存在的文件抛出异常"""
        with pytest.raises(FileNotFoundError):
            mock_cloud.download_file("nonexistent.txt", "/tmp/dummy.txt")

    def test_delete_nonexistent_no_error(self, mock_cloud):
        """测试删除不存在的文件不抛异常"""
        # delete_file不应该抛异常
        mock_cloud.delete_file("nonexistent.txt")

    def test_get_hash_nonexistent_raises(self, mock_cloud):
        """测试获取不存在文件的hash抛出异常"""
        with pytest.raises(FileNotFoundError):
            mock_cloud.get_file_hash("nonexistent.txt")
