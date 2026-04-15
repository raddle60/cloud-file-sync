from abc import ABC, abstractmethod
from typing import List

class CloudStorage(ABC):
    @abstractmethod
    def list_files(self, prefix: str = "") -> List[str]:
        """列出云端所有文件"""
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> None:
        """下载文件到本地"""
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> None:
        """上传文件到云端"""
        pass

    @abstractmethod
    def delete_file(self, remote_path: str) -> None:
        """删除云端文件"""
        pass

    @abstractmethod
    def rename_file(self, old_path: str, new_path: str) -> None:
        """重命名云端文件"""
        pass

    @abstractmethod
    def get_file_hash(self, remote_path: str) -> str:
        """获取云端文件hash值（如支持）"""
        pass

    @abstractmethod
    def get_file_size(self, remote_path: str) -> int:
        """获取云端文件大小"""
        pass
