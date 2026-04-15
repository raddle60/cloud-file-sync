from dataclasses import dataclass

@dataclass
class SyncPair:
    local: str
    remote: str
