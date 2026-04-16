"""
LocalMockCloudStorage - 基于本地目录的Mock云存储实现

用于单元测试，模拟云端存储行为，文件实际存储在本地文件系统中。
"""
import os
import shutil
import hashlib
import time
from typing import List, Optional
from cloud.base import CloudStorage


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
            base_dir: 模拟云端的根目录
            bucket_name: 模拟的bucket名称，用于隔离不同用户的存储
        """
        self.base_dir = os.path.abspath(base_dir)
        self.bucket_name = bucket_name
        self.bucket_dir = os.path.join(self.base_dir, bucket_name)
        os.makedirs(self.bucket_dir, exist_ok=True)

    def _resolve_remote_path(self, remote_path: str) -> str:
        """
        将云端路径转换为本地文件系统路径

        Args:
            remote_path: 云端路径，如 "bucket/prefix/file.txt"

        Returns:
            本地文件系统路径
        """
        # 移除bucket名前缀（如果存在）
        if remote_path.startswith(self.bucket_name):
            remote_path = remote_path[len(self.bucket_name):].lstrip('/')

        # 转换为本地路径
        local_path = os.path.join(self.bucket_dir, remote_path)
        return local_path

    def _get_bucket_prefix(self) -> str:
        """获取bucket路径前缀"""
        return f"{self.bucket_name}/"

    def list_files(self, prefix: str = "", is_include_tmp: bool = False) -> List[str]:
        """
        列出云端所有文件

        Args:
            prefix: 路径前缀过滤
            is_include_tmp: 是否包含.tmp文件

        Returns:
            文件路径列表
        """
        prefix_to_list = prefix
        # 如果prefix不以bucket_name开头，加上bucket前缀
        if prefix_to_list and not prefix_to_list.startswith(self.bucket_name):
            prefix_to_list = self._get_bucket_prefix() + prefix_to_list
        elif not prefix_to_list:
            prefix_to_list = self._get_bucket_prefix()

        prefix_to_list = prefix_to_list.rstrip('/') + '/'

        results = []
        prefix_len = len(self.bucket_dir) + 1  # +1 for the path separator

        for dirpath, dirnames, filenames in os.walk(self.bucket_dir):
            for filename in filenames:
                # 根据 is_include_tmp 参数决定是否跳过临时文件
                if not is_include_tmp and filename.endswith('.tmp'):
                    continue

                full_path = os.path.join(dirpath, filename)
                relative_path = full_path[prefix_len:]

                # 构建云端路径格式
                cloud_path = f"{self.bucket_name}/{relative_path.replace(os.sep, '/')}"

                # 应用前缀过滤
                if cloud_path.startswith(prefix_to_list.replace(os.sep, '/')):
                    results.append(cloud_path)

        return results

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """
        上传文件到云端

        Args:
            local_path: 本地文件路径
            remote_path: 云端目标路径
        """
        local_target = self._resolve_remote_path(remote_path)

        # 确保目录存在
        os.makedirs(os.path.dirname(local_target) or self.bucket_dir, exist_ok=True)

        # 复制文件
        shutil.copy2(local_path, local_target)

    def download_file(self, remote_path: str, local_path: str) -> None:
        """
        从云端下载文件到本地

        Args:
            remote_path: 云端文件路径
            local_path: 本地目标路径
        """
        local_source = self._resolve_remote_path(remote_path)

        if not os.path.exists(local_source):
            raise FileNotFoundError(f"Cloud file not found: {remote_path}")

        # 确保本地目录存在
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)

        # 复制文件
        shutil.copy2(local_source, local_path)

    def delete_file(self, remote_path: str) -> None:
        """
        删除云端文件

        Args:
            remote_path: 云端文件路径
        """
        local_path = self._resolve_remote_path(remote_path)

        if os.path.exists(local_path):
            os.unlink(local_path)

    def rename_file(self, old_path: str, new_path: str) -> None:
        """
        重命名云端文件（先复制再删除，实现原子替换）

        Args:
            old_path: 原路径
            new_path: 新路径
        """
        old_local = self._resolve_remote_path(old_path)
        new_local = self._resolve_remote_path(new_path)

        if not os.path.exists(old_local):
            raise FileNotFoundError(f"Cloud file not found: {old_path}")

        # 确保目标目录存在
        os.makedirs(os.path.dirname(new_local) or self.bucket_dir, exist_ok=True)

        # 重命名
        os.rename(old_local, new_local)

    def get_file_hash(self, remote_path: str) -> str:
        """
        获取云端文件hash值

        Args:
            remote_path: 云端文件路径

        Returns:
            SHA256哈希值
        """
        local_path = self._resolve_remote_path(remote_path)

        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Cloud file not found: {remote_path}")

        sha256 = hashlib.sha256()
        with open(local_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def get_file_size(self, remote_path: str) -> int:
        """
        获取云端文件大小

        Args:
            remote_path: 云端文件路径

        Returns:
            文件大小（字节）
        """
        local_path = self._resolve_remote_path(remote_path)

        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Cloud file not found: {remote_path}")

        return os.path.getsize(local_path)

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
