from dataclasses import dataclass, field
from typing import List
import json

from cloud_file_sync.models.sync_pair import SyncPair

@dataclass
class Config:
    encryption_enabled: bool
    encryption_key: str
    sync_pairs: List[SyncPair] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        sync_pairs = [SyncPair(**sp) for sp in data.get('sync_pairs', [])]
        return cls(
            encryption_enabled=data.get('encryption_enabled', False),
            encryption_key=data.get('encryption_key', ''),
            sync_pairs=sync_pairs
        )

class ConfigLoader:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def load(self) -> Config:
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return Config.from_dict(data)