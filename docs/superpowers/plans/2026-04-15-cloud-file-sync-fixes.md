# 云端双向同步工具 - 修复实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复3个关键问题：
1. 云端路径冲突检测
2. 实现 atomic_download 和周期性云端检查（60秒）
3. 配置文件中增加 cloud_type

**Tech Stack:** Python 3.9+, watchdog, bce-python-sdk, pycryptodome

---

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `cloud_file_sync/config/config_loader.py` | 添加 `cloud_type` 字段，添加 `validate_remote_paths()` 方法 |
| `cloud_file_sync/models/sync_pair.py` | 添加 `CloudType` 枚举 |
| `cloud_file_sync/core/sync_engine.py` | 实现 `check_cloud_changes()` 方法，实现 `download_from_cloud()` 方法 |
| `cloud_file_sync/core/file_watcher.py` | 添加周期性云端检查（60秒） |
| `cloud_file_sync/main.py` | 更新配置加载，使用 `cloud_type` 创建云端适配器 |
| `tests/test_config_loader.py` | 添加云端路径冲突测试 |
| `tests/test_sync_engine.py` | 添加 cloud change detection 测试 |

---

## Task 1: 配置验证 - 云端路径冲突检测

**Files:**
- Modify: `cloud_file_sync/config/config_loader.py`
- Modify: `cloud_file_sync/models/sync_pair.py`
- Create: `tests/test_config_loader.py` (add tests)

**Step 1: 添加 CloudType 枚举到 models/sync_pair.py**

```python
# cloud_file_sync/models/sync_pair.py
from dataclasses import dataclass, field
from typing import List
from enum import Enum

class CloudType(Enum):
    BAIDU_BOS = "baidu_bos"

@dataclass
class SyncPair:
    local: str
    remote: str
    encryption_enabled: bool = False
```

**Step 2: 更新 Config 数据类和添加验证方法**

```python
# cloud_file_sync/config/config_loader.py
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
            # 检查是否与其他 remote 冲突
            for existing in remotes:
                if remote.startswith(existing + '/') or existing.startswith(remote + '/'):
                    raise ValueError(
                        f"Remote path conflict: '{remote}' is inside '{existing}'"
                    )
            remotes.append(remote)
```

**Step 3: 添加测试**

```python
# tests/test_config_loader.py (add these tests)

def test_config_cloud_type():
    config_data = {
        "cloud_type": "baidu_bos",
        "encryption_enabled": False,
        "encryption_key": "key",
        "sync_pairs": []
    }
    loader = ConfigLoader(temp_path)
    config = loader.load()
    assert config.cloud_type == CloudType.BAIDU_BOS

def test_config_remote_path_conflict():
    """测试 remote 路径冲突检测"""
    config_data = {
        "cloud_type": "baidu_bos",
        "encryption_enabled": False,
        "encryption_key": "key",
        "sync_pairs": [
            {"local": "/local1", "remote": "bucket/prefix1/"},
            {"local": "/local2", "remote": "bucket/prefix1/subdir/"}  # 冲突！
        ]
    }
    # 应该抛出 ValueError
```

Run tests, commit.

---

## Task 2: 实现云端变更检测

**Files:**
- Modify: `cloud_file_sync/core/sync_engine.py`
- Create: `tests/test_sync_engine.py` (add tests)

**Step 1: 添加 check_cloud_changes 方法到 SyncEngine**

```python
# cloud_file_sync/core/sync_engine.py

# 在 SyncEngine 类中添加：

def get_last_cloud_metas(self) -> Dict[str, FileMeta]:
    """获取内存中保存的上次云端meta信息"""
    return self._last_cloud_metas.copy()

def set_last_cloud_metas(self, metas: Dict[str, FileMeta]):
    """更新内存中保存的云端meta信息"""
    self._last_cloud_metas = metas.copy()

def check_cloud_changes(self) -> List[Dict]:
    """
    检查云端变化，返回有变化的文件列表
    返回格式: [{"type": "new"|"modified"|"deleted", "cloud_name": str, "meta": FileMeta}]
    """
    # 1. 获取当前云端所有文件
    cloud_files = self.cloud_storage.list_files(self.sync_pair.remote)

    # 2. 解析meta文件
    current_metas = {}
    for f in cloud_files:
        if f.endswith('.meta.json'):
            try:
                meta = self._download_and_read_meta(f)
                # 从meta中获取原始cloud_name（去掉.meta.json后缀）
                cloud_name = f[:-len('.meta.json')]
                current_metas[cloud_name] = meta
            except Exception:
                continue

    # 3. 与上次保存的meta对比
    last_metas = self.get_last_cloud_metas()
    changes = []

    # 新增或修改
    for cloud_name, meta in current_metas.items():
        if cloud_name not in last_metas:
            changes.append({"type": "new", "cloud_name": cloud_name, "meta": meta})
        elif last_metas[cloud_name].sha256 != meta.sha256:
            changes.append({"type": "modified", "cloud_name": cloud_name, "meta": meta})

    # 删除
    for cloud_name in last_metas:
        if cloud_name not in current_metas:
            changes.append({"type": "deleted", "cloud_name": cloud_name, "meta": last_metas[cloud_name]})

    # 4. 更新保存的meta
    self.set_last_cloud_metas(current_metas)

    return changes

def _download_and_read_meta(self, meta_path: str) -> FileMeta:
    """下载并解析meta文件"""
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    try:
        self.cloud_storage.download_file(meta_path, tmp_path)

        if self.sync_pair.encryption_enabled and self.crypto:
            decrypted_tmp = tmp_path + ".dec"
            self.crypto.decrypt_file(tmp_path, decrypted_tmp)
            os.unlink(tmp_path)
            tmp_path = decrypted_tmp

        return self.meta_manager.read_meta(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
```

**Step 2: 添加测试**

```python
# tests/test_sync_engine.py (add)

def test_check_cloud_changes_new_file():
    """测试检测云端新增文件"""
    # mock cloud storage returns new file
    # verify change detection works
```

Run tests, commit.

---

## Task 3: 实现 download_from_cloud

**Files:**
- Modify: `cloud_file_sync/core/sync_engine.py`

**Step 1: 添加 download_from_cloud 方法**

```python
# cloud_file_sync/core/sync_engine.py

def download_from_cloud(self, cloud_name: str, meta: FileMeta) -> None:
    """
    从云端下载文件到本地
    """
    # 1. 获取本地路径
    relative_path = meta.relative_path
    local_path = self.get_local_path(relative_path)

    # 2. 确保目录存在
    os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)

    # 3. 云端文件路径
    cloud_path = self.get_cloud_path(relative_path)

    # 4. 原子下载
    self.atomic_download(cloud_path, local_path, meta.sha256)
```

**Step 2: 更新 full_sync 以支持双向同步**

```python
def full_sync(self):
    """执行全量同步"""
    # 1. 扫描本地文件
    self.scan_local_files()

    # 2. 获取云端文件列表
    cloud_files = self.cloud_storage.list_files(self.sync_pair.remote)

    # 3. 解析云端meta文件，保存到内存
    cloud_metas = {}
    for f in cloud_files:
        if f.endswith('.meta.json'):
            try:
                meta = self._download_and_read_meta(f)
                cloud_name = f[:-len('.meta.json')]
                cloud_metas[cloud_name] = meta
            except Exception:
                continue

    # 4. 先更新保存的meta（用于后续变化检测）
    self.set_last_cloud_metas(cloud_metas)

    # 5. 全量对比和同步
    # ... (原有逻辑)

    # 6. 初始化时下载所有云端文件到本地
    for cloud_name, meta in cloud_metas.items():
        local_path = self.get_local_path(meta.relative_path)
        if not os.path.exists(local_path):
            cloud_path = self.get_cloud_path(meta.relative_path)
            self.atomic_download(cloud_path, local_path, meta.sha256)
```

Run tests, commit.

---

## Task 4: 更新 FileWatcher 添加周期性云端检查

**Files:**
- Modify: `cloud_file_sync/core/file_watcher.py`
- Modify: `cloud_file_sync/main.py`

**Step 1: 添加周期性检查到 FileWatcher**

```python
# cloud_file_sync/core/file_watcher.py

import threading
import time

class PeriodicChecker:
    """周期性任务检查器"""
    def __init__(self, interval_seconds: float, callback):
        self.interval = interval_seconds
        self.callback = callback
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(self.interval)
            if not self._stop_event.is_set():
                self.callback()

class FileWatcher:
    def __init__(self, watch_path: str, debounce_seconds: float = 10.0,
                 callback=None, periodic_callback=None, periodic_interval: float = 60.0):
        # ... existing code ...

        self.periodic_callback = periodic_callback
        self.periodic_checker = None
        if periodic_callback:
            self.periodic_checker = PeriodicChecker(periodic_interval, periodic_callback)

    def start(self):
        self._observer.schedule(self._handler, self.watch_path, recursive=True)
        self._observer.start()
        if self.periodic_checker:
            self.periodic_checker.start()

    def stop(self):
        if self.periodic_checker:
            self.periodic_checker.stop()
        self._observer.stop()
        self._observer.join()
```

**Step 2: 更新 main.py 使用 periodic_callback**

```python
# cloud_file_sync/main.py

def start_sync(config_path: str, daemon: bool = False):
    # ... existing code ...

    def on_periodic_check():
        for engine in engines:
            changes = engine.check_cloud_changes()
            for change in changes:
                if change['type'] == 'new':
                    engine.download_from_cloud(change['cloud_name'], change['meta'])
                elif change['type'] == 'modified':
                    # 比较本地和云端，决定是否下载
                    pass
                elif change['type'] == 'deleted':
                    # 删除本地文件
                    pass

    # 创建文件监听器
    _global_watcher = FileWatcher(
        watch_path=config.sync_pairs[0].local,
        debounce_seconds=10.0,
        callback=on_file_changed,
        periodic_callback=on_periodic_check,
        periodic_interval=60.0
    )
```

Run tests, commit.

---

## Task 5: 更新配置创建云端适配器

**Files:**
- Modify: `cloud_file_sync/main.py`

**Step 1: 更新 create_cloud_storage 支持 cloud_type**

```python
# cloud_file_sync/main.py

def create_cloud_storage(config: Config):
    """根据 cloud_type 创建云端存储实例"""
    if not config.sync_pairs:
        raise ValueError("No sync_pairs configured")

    if config.cloud_type == CloudType.BAIDU_BOS:
        return BaiduBOS(
            access_key_id=os.environ.get('BOS_ACCESS_KEY_ID', ''),
            access_key_secret=os.environ.get('BOS_ACCESS_KEY_SECRET', ''),
            endpoint=os.environ.get('BOS_ENDPOINT', ''),
            bucket_name=config.sync_pairs[0].remote.split('/')[0]
        )
    else:
        raise ValueError(f"Unsupported cloud_type: {config.cloud_type}")
```

Run tests, commit.

---

## 验证清单

- [ ] 配置加载支持 cloud_type
- [ ] 同一云端目录冲突检测生效
- [ ] check_cloud_changes 能检测新增/修改/删除
- [ ] atomic_download 正常工作
- [ ] 周期性云端检查（60秒）正常工作
- [ ] 全量同步时下载云端文件到本地
- [ ] 所有原有测试继续通过
