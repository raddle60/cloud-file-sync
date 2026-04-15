from dataclasses import dataclass, field
from typing import List
import json

from cloud_file_sync.models.sync_pair import SyncPair, CloudType

@dataclass
class Config:
    cloud_type: CloudType
    encryption_enabled: bool
    encryption_key: str
    sync_pairs: List[SyncPair] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        cloud_type_str = data.get('cloud_type', 'baidu_bos')
        try:
            cloud_type = CloudType(cloud_type_str)
        except ValueError:
            raise ValueError(f"Unknown cloud_type: {cloud_type_str}")

        sync_pairs = [SyncPair(**sp) for sp in data.get('sync_pairs', [])]
        return cls(
            cloud_type=cloud_type,
            encryption_enabled=data.get('encryption_enabled', False),
            encryption_key=data.get('encryption_key', ''),
            sync_pairs=sync_pairs
        )

    def validate_remote_paths(self) -> None:
        """验证所有 sync_pairs 的 remote 路径不冲突"""
        remotes = []
        for sp in self.sync_pairs:
            remote = sp.remote.rstrip('/')
            for existing in remotes:
                if remote.startswith(existing + '/') or existing.startswith(remote + '/'):
                    raise ValueError(
                        f"Remote path conflict: '{remote}' is inside '{existing}'"
                    )
            remotes.append(remote)

class ConfigLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def load(self) -> Config:
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return Config.from_dict(data)