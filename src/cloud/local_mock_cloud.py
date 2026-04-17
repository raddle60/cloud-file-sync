"""
LocalMockCloudStorage - 基于本地目录的Mock云存储实现

用于单元测试，模拟云端存储行为，文件实际存储在本地文件系统中。
"""
import os
import shutil
import hashlib
import time
from typing import List, Optional
from cloud.base import CloudStorage, FileInfo
from utils.path_util import PathUtil


class LocalMockCloudStorage(CloudStorage):
    """
    基于本地目录的Mock云存储

    特点：
    - 将云端存储模拟为本地文件系统中的一个目录
    - 支持CloudStorage ABC的所有方法
    - 可配置bucket前缀模拟多bucket环境
    - 支持加密和非加密模式（通过外部配置）
    """

    def __init__(self, base_dir: str, bucket_name: str = "mock-bucket"):
        """
        初始化LocalMockCloudStorage

        Args:
            base_dir: 模拟云端的根目录（必须存在）
            bucket_name: 模拟的bucket名称，用于隔离不同用户的存储

        Raises:
            FileNotFoundError: 当 base_dir 不存在时抛出
        """
        self.base_dir = os.path.abspath(base_dir)
        if not os.path.isdir(self.base_dir):
            raise FileNotFoundError("LocalMockCloudStorage base_dir does not exist: " + self.base_dir)
        self.bucket_name = bucket_name
        self.bucket_dir = PathUtil.join(self.base_dir, bucket_name)
        os.makedirs(self.bucket_dir, exist_ok=True)

    def _resolve_remote_path(self, remote_path: str) -> str:
        """
        将云端路径转换为本地文件系统路径

        Args:
            remote_path: 云端路径，如 "bucket/prefix/file.txt"

        Returns:
            本地文件系统路径
        """
        # 如果本地路径已经包含bucket前缀，说明是完整路径
        if remote_path.startswith(self.bucket_dir):
            return remote_path

        # 转换为本地路径
        local_path = PathUtil.join(self.bucket_dir, remote_path)
        return local_path

    def _get_bucket_prefix(self) -> str:
        """获取bucket路径前缀"""
        return f"{self.bucket_name}/"

    def list_files(
        self,
        prefix: str = "",
        is_include_tmp: bool = False,
        recursive: bool = True,
        include_dirs: bool = False
    ) -> List[FileInfo]:
        prefix_path = PathUtil.join(self.bucket_dir, prefix).replace(os.sep, '/')
        results = []
        prefix_len = len(self.bucket_dir)

        for dirpath, dirnames, filenames in os.walk(self.bucket_dir):
            # 处理目录（如果 include_dirs=True）
            if include_dirs:
                rel_dir = dirpath[prefix_len:].replace(os.sep, '/').lstrip('/')
                if rel_dir and (not prefix or rel_dir.startswith(prefix.replace('\\', '/'))):
                    # Construct cloud_path consistent with file case
                    if self.bucket_name:
                        cloud_dir_path = f"{self.bucket_name}/{rel_dir}"
                    else:
                        cloud_dir_path = rel_dir
                    results.append(FileInfo(
                        file_id=cloud_dir_path,
                        file_path=cloud_dir_path,
                        size=None,
                        file_hash=None,
                        hash_algo=None,
                        local_mtime=int(os.stat(dirpath).st_mtime),
                        isdir=True
                    ))

            for filename in filenames:
                # 过滤 tmp 文件
                if not is_include_tmp and filename.endswith('.tmp'):
                    continue

                full_path = PathUtil.join(dirpath, filename).replace(os.sep, '/')
                relative_path = full_path[prefix_len:].lstrip(os.sep).lstrip('/').replace(os.sep, '/')
                # Construct cloud_path consistent with upload_file
                if self.bucket_name:
                    cloud_path = f"{self.bucket_name}/{relative_path}"
                else:
                    cloud_path = relative_path

                # 应用前缀过滤（非递归情况下只匹配直接子项）
                if not recursive:
                    if '/' in relative_path and not relative_path.startswith(prefix.replace('\\', '/').rstrip('/')):
                        continue

                if full_path.startswith(prefix_path.replace('\\', '/')):
                    stat = os.stat(full_path)
                    sha256 = hashlib.sha256()
                    with open(full_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(8192), b''):
                            sha256.update(chunk)

                    results.append(FileInfo(
                        file_id=cloud_path,
                        file_path=cloud_path,
                        size=stat.st_size,
                        file_hash=sha256.hexdigest(),
                        hash_algo='sha256',
                        local_mtime=int(stat.st_mtime),
                        isdir=False
                    ))

        return results

    def upload_file(self, local_path: str, remote_path: str) -> FileInfo:
        local_target = self._resolve_remote_path(remote_path)
        os.makedirs(os.path.dirname(local_target) or self.bucket_dir, exist_ok=True)
        shutil.copy2(local_path, local_target)

        stat = os.stat(local_path)
        sha256 = hashlib.sha256()
        with open(local_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)

        # Construct cloud_path consistent with list_files
        # Use remote_path directly when bucket_name is empty to avoid leading slash
        if self.bucket_name:
            cloud_path = f"{self.bucket_name}/{remote_path}"
        else:
            cloud_path = remote_path

        return FileInfo(
            file_id=cloud_path,
            file_path=cloud_path,
            size=stat.st_size,
            file_hash=sha256.hexdigest(),
            hash_algo='sha256',
            local_mtime=int(stat.st_mtime),
            isdir=False
        )

    def download_file(
        self,
        file_id: Optional[str],
        remote_path: str,
        local_path: str
    ) -> None:
        # file_id 参数 LocalMockCloud 不使用，直接用 remote_path
        local_source = self._resolve_remote_path(remote_path)
        if not os.path.exists(local_source):
            raise FileNotFoundError(f"Cloud file not found: {remote_path}")
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        shutil.copy2(local_source, local_path)

    def delete_file(self, file_id: Optional[str], remote_path: str) -> None:
        # file_id 参数 LocalMockCloud 不使用，直接用 remote_path
        local_path = self._resolve_remote_path(remote_path)
        if os.path.exists(local_path):
            os.unlink(local_path)

    def rename_file(
        self,
        file_id: Optional[str],
        old_path: str,
        new_path: str
    ) -> FileInfo:
        # file_id 参数 LocalMockCloud 不使用，直接用路径
        old_local = self._resolve_remote_path(old_path)
        new_local = self._resolve_remote_path(new_path)

        if not os.path.exists(old_local):
            raise FileNotFoundError(f"Cloud file not found: {old_path}")

        os.makedirs(os.path.dirname(new_local) or self.bucket_dir, exist_ok=True)
        os.rename(old_local, new_local)

        # 返回新文件的 FileInfo
        return FileInfo(
            file_id=new_path,
            file_path=new_path,
            size=os.path.getsize(new_local),
            file_hash=None,
            hash_algo=None,
            local_mtime=int(os.path.getmtime(new_local)),
            isdir=False
        )

    def file_exists(self, remote_path: str) -> bool:
        """
        检查文件是否存在

        Args:
            remote_path: 云端文件路径

        Returns:
            是否存在
        """
        local_path = self._resolve_remote_path(remote_path)
        return os.path.exists(local_path)

    def get_last_modified(self, remote_path: str) -> int:
        """
        获取文件最后修改时间

        Args:
            remote_path: 云端文件路径

        Returns:
            Unix时间戳
        """
        local_path = self._resolve_remote_path(remote_path)

        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Cloud file not found: {remote_path}")

        return int(os.stat(local_path).st_mtime)

    def cleanup(self) -> None:
        """清理所有存储的文件"""
        if os.path.exists(self.bucket_dir):
            shutil.rmtree(self.bucket_dir)
        os.makedirs(self.bucket_dir, exist_ok=True)
