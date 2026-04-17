from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FileInfo:
    file_id: Optional[str]     # 云端唯一标识，可能为 None
    file_path: str              # 云端文件路径
    size: Optional[int]         # 文件大小，可能为 None
    file_hash: Optional[str]    # 文件 hash，可能为 None
    hash_algo: Optional[str]    # hash 算法，默认 None
    local_mtime: Optional[int]  # 最后修改时间，可能为 None
    isdir: bool                 # 是否为目录


class CloudStorage(ABC):
    @abstractmethod
    def list_files(
        self,
        prefix: str = "",
        is_include_tmp: bool = False,
        recursive: bool = True,
        include_dirs: bool = False
    ) -> List[FileInfo]:
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> FileInfo:
        pass

    @abstractmethod
    def download_file(
        self,
        file_id: Optional[str],
        remote_path: str,
        local_path: str
    ) -> None:
        pass

    @abstractmethod
    def delete_file(self, file_id: Optional[str], remote_path: str) -> None:
        pass

    @abstractmethod
    def rename_file(
        self,
        file_id: Optional[str],
        old_path: str,
        new_path: str
    ) -> FileInfo:
        pass
