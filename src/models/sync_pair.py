from dataclasses import dataclass
from typing import Optional
from enum import Enum

class CloudType(Enum):
    BAIDU_BOS = "baidu_bos"
    LOCAL_MOCK = "local_mock"

@dataclass
class SyncPair:
    local: str
    remote: str
    encryption_enabled: bool = False

@dataclass
class FileMeta:
    """文件Meta信息"""
    original_filename: str
    size: int
    last_modified: int  # Unix timestamp
    sha256: str
    relative_path: str = ""  # 相对于sync_pair的路径

    def to_dict(self) -> dict:
        return {
            "original_filename": self.original_filename,
            "size": self.size,
            "last_modified": self.last_modified,
            "sha256": self.sha256,
            "relative_path": self.relative_path
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'FileMeta':
        return cls(
            original_filename=data["original_filename"],
            size=data["size"],
            last_modified=data["last_modified"],
            sha256=data["sha256"],
            relative_path=data.get("relative_path", "")
        )
