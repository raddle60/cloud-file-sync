# CloudStorage 基类改造实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改造 CloudStorage ABC，新增 FileInfo 数据类，调整方法签名，适配云端新接口

**Architecture:**
- 新增 `FileInfo` 数据类统一文件元信息
- CloudStorage ABC 方法签名调整：download/delete/rename 增加 file_id 参数，upload/rename 返回 FileInfo
- list_files 返回 `List[FileInfo]` 替代 `List[str]`
- 移除 get_file_hash 和 get_file_size 方法
- SyncEngine 调用方适配新接口

**Tech Stack:** Python dataclass, ABC abstractmethod

---

## 文件结构

```
src/cloud/base.py          # CloudStorage ABC + FileInfo 数据类
src/cloud/baidu_bos.py     # BaiduBOS 实现更新
src/cloud/local_mock_cloud.py  # LocalMockCloudStorage 实现更新
src/core/sync_engine.py    # SyncEngine 调用适配
tests/test_local_mock_cloud.py  # 测试更新
```

---

## Task 1: 修改 CloudStorage ABC - 新增 FileInfo 和方法签名

**Files:**
- Modify: `src/cloud/base.py`

- [ ] **Step 1: 添加 FileInfo 数据类**

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class FileInfo:
    file_id: Optional[str]     # 云端唯一标识，可能为 None
    file_path: str              # 云端文件路径
    size: Optional[int]         # 文件大小，可能为 None
    file_hash: Optional[str]    # 文件 hash，可能为 None
    hash_algo: Optional[str]    # hash 算法，默认 None
    local_mtime: Optional[int]  # 最后修改时间，可能为 None
    isdir: bool                 # 是否为目录
```

- [ ] **Step 2: 修改 CloudStorage ABC 方法签名**

```python
from abc import ABC, abstractmethod
from typing import List

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
```

- [ ] **Step 3: 移除 get_file_hash 和 get_file_size 方法**

删除以下两个方法：
```python
# 删除
@abstractmethod
def get_file_hash(self, remote_path: str) -> str:
    pass

@abstractmethod
def get_file_size(self, remote_path: str) -> int:
    pass
```

- [ ] **Step 4: 提交**

```bash
git add src/cloud/base.py
git commit -m "feat: add FileInfo dataclass and update CloudStorage ABC signatures"
```

---

## Task 2: 更新 BaiduBOS 实现

**Files:**
- Modify: `src/cloud/baidu_bos.py`

- [ ] **Step 1: 更新 import 和方法签名**

```python
import os
from typing import List, Optional
from baidubce.services.bos.bos_client import BosClient, bce_client_configuration
from baidubce.auth.bce_credentials import BceCredentials
from cloud.base import CloudStorage, FileInfo
```

- [ ] **Step 2: 实现 list_files 返回 FileInfo 列表**

```python
def list_files(
    self,
    prefix: str = "",
    is_include_tmp: bool = False,
    recursive: bool = True,
    include_dirs: bool = False
) -> List[FileInfo]:
    # 使用 BoseClient 的 list_objects 方法
    response = self.bos_client.list_objects(self.bucket_name, prefix=prefix)
    contents = response.get('contents', [])

    results = []
    for item in contents:
        key = item['key']

        # 过滤 tmp 文件
        if not is_include_tmp and key.endswith('.tmp'):
            continue

        # 构建 FileInfo
        file_info = FileInfo(
            file_id=key,  # BaiduBOS 使用 key 作为 file_id
            file_path=key,
            size=int(item.get('size', 0)),
            file_hash=item.get('etag', ''),  # BOS 使用 ETag
            hash_algo='etag',
            local_mtime=self._parse_bos_time(item.get('last_modified', '')),
            isdir=False
        )
        results.append(file_info)

    return results

def _parse_bos_time(self, timestr: str) -> Optional[int]:
    """解析 BOS 时间字符串为 Unix timestamp"""
    from datetime import datetime
    if not timestr:
        return None
    try:
        # BOS 时间格式: 2024-01-01T00:00:00Z
        dt = datetime.strptime(timestr, "%Y-%m-%dT%H:%M:%SZ")
        return int(dt.timestamp())
    except:
        return None
```

- [ ] **Step 3: 实现 upload_file 返回 FileInfo**

```python
def upload_file(self, local_path: str, remote_path: str) -> FileInfo:
    self.bos_client.put_object_from_file(
        self.bucket_name, remote_path, local_path
    )
    # 返回 FileInfo
    return FileInfo(
        file_id=remote_path,  # BOS 使用路径作为 ID
        file_path=remote_path,
        size=os.path.getsize(local_path),
        file_hash=None,
        hash_algo=None,
        local_mtime=int(os.path.getmtime(local_path)),
        isdir=False
    )
```

- [ ] **Step 4: 实现 download_file（新增 file_id 参数）**

```python
def download_file(
    self,
    file_id: Optional[str],
    remote_path: str,
    local_path: str
) -> None:
    # file_id 参数 BaiduBOS 不使用，直接用 remote_path
    os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
    self.bos_client.get_object_to_file(self.bucket_name, remote_path, local_path)
```

- [ ] **Step 5: 实现 delete_file（新增 file_id 参数）**

```python
def delete_file(self, file_id: Optional[str], remote_path: str) -> None:
    # file_id 参数 BaiduBOS 不使用，直接用 remote_path
    self.bos_client.delete_object(self.bucket_name, remote_path)
```

- [ ] **Step 6: 实现 rename_file（新增 file_id 参数，返回 FileInfo）**

```python
def rename_file(
    self,
    file_id: Optional[str],
    old_path: str,
    new_path: str
) -> FileInfo:
    # 复制到新路径
    self.bos_client.copy_object(
        self.bucket_name, new_path,
        self.bucket_name, old_path
    )
    # 删除旧路径
    self.bos_client.delete_object(self.bucket_name, old_path)

    # 返回新文件的 FileInfo
    return FileInfo(
        file_id=new_path,
        file_path=new_path,
        size=None,
        file_hash=None,
        hash_algo=None,
        local_mtime=None,
        isdir=False
    )
```

- [ ] **Step 7: 移除 get_file_hash 和 get_file_size 方法**

删除 baidu_bos.py 中的：
```python
def get_file_hash(self, remote_path: str) -> str:
    ...

def get_file_size(self, remote_path: str) -> int:
    ...
```

- [ ] **Step 8: 提交**

```bash
git add src/cloud/baidu_bos.py
git commit -m "feat: update BaiduBOS to new CloudStorage interface"
```

---

## Task 3: 更新 LocalMockCloudStorage 实现

**Files:**
- Modify: `src/cloud/local_mock_cloud.py`

- [ ] **Step 1: 更新 import**

```python
from cloud.base import CloudStorage, FileInfo
```

- [ ] **Step 2: 实现 list_files 返回 FileInfo 列表**

```python
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
                results.append(FileInfo(
                    file_id=rel_dir,
                    file_path=f"{self.bucket_name}/{rel_dir}",
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
            relative_path = full_path[prefix_len:].lstrip(os.sep).replace(os.sep, '/')
            cloud_path = f"{self.bucket_name}/{relative_path}"

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
```

- [ ] **Step 3: 实现 upload_file 返回 FileInfo**

```python
def upload_file(self, local_path: str, remote_path: str) -> FileInfo:
    local_target = self._resolve_remote_path(remote_path)
    os.makedirs(os.path.dirname(local_target) or self.bucket_dir, exist_ok=True)
    shutil.copy2(local_path, local_target)

    stat = os.stat(local_path)
    sha256 = hashlib.sha256()
    with open(local_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)

    return FileInfo(
        file_id=remote_path,
        file_path=remote_path,
        size=stat.st_size,
        file_hash=sha256.hexdigest(),
        hash_algo='sha256',
        local_mtime=int(stat.st_mtime),
        isdir=False
    )
```

- [ ] **Step 4: 实现 download_file（新增 file_id 参数）**

```python
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
```

- [ ] **Step 5: 实现 delete_file（新增 file_id 参数）**

```python
def delete_file(self, file_id: Optional[str], remote_path: str) -> None:
    # file_id 参数 LocalMockCloud 不使用，直接用 remote_path
    local_path = self._resolve_remote_path(remote_path)
    if os.path.exists(local_path):
        os.unlink(local_path)
```

- [ ] **Step 6: 实现 rename_file（新增 file_id 参数，返回 FileInfo）**

```python
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
```

- [ ] **Step 7: 移除 get_file_hash 和 get_file_size 方法**

删除 local_mock_cloud.py 中的：
```python
def get_file_hash(self, remote_path: str) -> str:
    ...

def get_file_size(self, remote_path: str) -> int:
    ...
```

- [ ] **Step 8: 提交**

```bash
git add src/cloud/local_mock_cloud.py
git commit -m "feat: update LocalMockCloudStorage to new CloudStorage interface"
```

---

## Task 4: 更新 SyncEngine 调用适配新接口

**Files:**
- Modify: `src/core/sync_engine.py`

- [ ] **Step 1: 检查所有 cloud_storage 调用**

SyncEngine 中以下调用需要适配：
1. `self.cloud_storage.list_files(...)` - 现在返回 `List[FileInfo]` 而非 `List[str]`
2. `self.cloud_storage.upload_file(...)` - 现在返回 `FileInfo`
3. `self.cloud_storage.download_file(...)` - 现在需要 `file_id` 参数
4. `self.cloud_storage.delete_file(...)` - 现在需要 `file_id` 参数
5. `self.cloud_storage.rename_file(...)` - 现在需要 `file_id` 参数并返回 `FileInfo`
6. `self.cloud_storage.get_file_hash(...)` - 已移除
7. `self.cloud_storage.get_file_size(...)` - 已移除

- [ ] **Step 2: 更新 list_files 调用处**

找到 `list_files` 调用的地方，适配新的 FileInfo 列表：

旧代码（大约 line 133-140）：
```python
cloud_files = self.cloud_storage.list_files(self.sync_pair.remote, is_include_tmp=True)
for f in cloud_files:
    fname = f.split('/')[-1]
    if fname == cloud_tmp_path or f == cloud_tmp_path:
        ...
```

新代码：
```python
cloud_files = self.cloud_storage.list_files(self.sync_pair.remote, is_include_tmp=True)
for file_info in cloud_files:
    fname = file_info.file_path.split('/')[-1]
    if fname == cloud_tmp_path or file_info.file_path == cloud_tmp_path:
        ...
```

类似地，其他 `list_files` 调用处需要从 `FileInfo.file_path` 获取路径。

- [ ] **Step 3: 更新 download_file 调用处**

旧代码（大约 line 261）：
```python
self.cloud_storage.download_file(cloud_path, tmp_path)
```

新代码：
```python
self.cloud_storage.download_file(None, cloud_path, tmp_path)
```

- [ ] **Step 4: 更新 delete_file 调用处**

找到 `delete_file` 调用处，添加 `None` 作为 `file_id`：

旧代码：
```python
self.cloud_storage.delete_file(cloud_path)
```

新代码：
```python
self.cloud_storage.delete_file(None, cloud_path)
```

- [ ] **Step 5: 更新 rename_file 调用处**

找到 `rename_file` 调用处，添加 `None` 作为 `file_id`：

旧代码：
```python
self.cloud_storage.rename_file(tmp_path, cloud_path)
```

新代码：
```python
self.cloud_storage.rename_file(None, tmp_path, cloud_path)
```

- [ ] **Step 6: 更新 get_file_hash 和 get_file_size 调用处**

在 `atomic_upload` 方法中（约 line 240-246）：

旧代码：
```python
cloud_hash = self.cloud_storage.get_file_hash(tmp_path)
local_hash = self._calc_sha256(local_path)
verified = (cloud_hash == local_hash)
...
cloud_size = self.cloud_storage.get_file_size(tmp_path)
local_size = os.path.getsize(local_path)
```

由于 `list_files` 现在返回 `FileInfo`，需要先调用 `list_files` 获取文件的 `file_hash` 和 `size`：

```python
# 获取云端文件信息
cloud_files = self.cloud_storage.list_files(prefix=self.sync_pair.remote, is_include_tmp=True)
cloud_info = None
for f in cloud_files:
    if f.file_path == tmp_path:
        cloud_info = f
        break

if cloud_info and cloud_info.file_hash:
    local_hash = self._calc_sha256(local_path)
    verified = (cloud_info.file_hash == local_hash)
else:
    local_size = os.path.getsize(local_path)
    verified = (cloud_info.size == local_size if cloud_info and cloud_info.size else False)
```

- [ ] **Step 7: 提交**

```bash
git add src/core/sync_engine.py
git commit -m "feat: update SyncEngine to use new CloudStorage interface"
```

---

## Task 5: 更新 LocalMockCloudStorage 测试

**Files:**
- Modify: `tests/test_local_mock_cloud.py`

- [ ] **Step 1: 更新 test_upload_and_list 测试**

旧代码检查 `files` 是字符串列表，新代码返回 `FileInfo` 列表：

```python
def test_upload_and_list(self, mock_cloud):
    # ... 上传代码不变 ...

    # 列出文件（不含tmp）
    files = mock_cloud.list_files()
    assert len(files) == 2
    assert any("test.txt" in f.file_path for f in files)  # 修改：f -> f.file_path
    assert any(".meta.json" in f.file_path for f in files)

    # 使用is_include_tmp=True列出文件，应包含temp文件
    all_files = mock_cloud.list_files(is_include_tmp=True)
    assert len(all_files) == 3
    assert any("test.txt" in f.file_path for f in all_files)
    assert any("test.txt.tmp" in f.file_path for f in all_files)
    assert any(".meta.json" in f.file_path for f in all_files)
```

- [ ] **Step 2: 更新 test_download_file 测试**

```python
def test_download_file(self, mock_cloud):
    # ... 创建文件 ...
    remote_path = "download_test.txt"
    mock_cloud.upload_file(local_path, remote_path)

    # 下载到新位置
    download_path = os.path.join(tempfile.gettempdir(), "downloaded.txt")
    mock_cloud.download_file(None, remote_path, download_path)  # 修改：添加 None
    # ... 其余代码不变 ...
```

- [ ] **Step 3: 更新 test_delete_file 测试**

```python
def test_delete_file(self, mock_cloud):
    # ... 创建文件 ...
    remote_path = "delete_test.txt"
    # ... 上传 ...
    mock_cloud.delete_file(None, remote_path)  # 修改：添加 None
    # ... 其余验证不变 ...
```

- [ ] **Step 4: 更新 test_rename_file 测试**

```python
def test_rename_file(self, mock_cloud):
    # ... 创建文件 ...
    old_path = "old_name.txt"
    new_path = "new_name.txt"
    # ... 上传 ...
    mock_cloud.rename_file(None, old_path, new_path)  # 修改：添加 None
    # ... 其余验证不变 ...
```

- [ ] **Step 5: 更新 test_get_file_hash 和 test_get_file_size 测试**

这两个测试测试的是已移除的方法，需要删除或修改为测试 `list_files` 返回的 `FileInfo`：

```python
def test_file_info_from_list(self, mock_cloud):
    """测试 list_files 返回的 FileInfo 包含 hash 和 size"""
    content = "Hash and size test"
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write(content)
        local_path = f.name

    try:
        remote_path = "info_test.txt"
        mock_cloud.upload_file(local_path, remote_path)

        files = mock_cloud.list_files()
        file_info = next((f for f in files if f.file_path == remote_path), None)
        assert file_info is not None
        assert file_info.size == len(content.encode('utf-8'))
        assert file_info.file_hash is not None
        assert len(file_info.file_hash) == 64  # SHA256
    finally:
        os.unlink(local_path)
```

- [ ] **Step 6: 更新 test_list_with_prefix 测试**

```python
def test_list_with_prefix(self, mock_cloud):
    # ... 上传文件 ...
    # 列出所有
    all_files = mock_cloud.list_files()
    assert len(all_files) == 3

    # 按前缀过滤
    folder1_files = mock_cloud.list_files("folder1/")
    assert len(folder1_files) == 2
```

- [ ] **Step 7: 更新 test_list_excludes_tmp_files 测试**

```python
def test_list_excludes_tmp_files(self, mock_cloud):
    # ... 上传正常文件 ...
    files = mock_cloud.list_files()
    # 应该不包含tmp文件
    assert all(not f.file_path.endswith('.tmp') for f in files)
```

- [ ] **Step 8: 更新 test_atomic_upload_simulation 测试**

```python
def test_atomic_upload_simulation(self, mock_cloud):
    # ...
    # 2. 验证 - 使用 list_files 获取 file_info
    cloud_files = mock_cloud.list_files(is_include_tmp=True)
    tmp_info = next((f for f in cloud_files if f.file_path == tmp_path), None)
    local_info = next((f for f in cloud_files if f.file_path == remote_path), None)

    hash1 = tmp_info.file_hash if tmp_info else None
    local_hash = local_info.file_hash if local_info else None
    # ...
```

- [ ] **Step 9: 更新 test_download_nonexistent_raises 测试**

```python
def test_download_nonexistent_raises(self, mock_cloud):
    with pytest.raises(FileNotFoundError):
        mock_cloud.download_file(None, "nonexistent.txt", "/tmp/dummy.txt")
```

- [ ] **Step 10: 更新 test_delete_nonexistent_no_error 测试**

```python
def test_delete_nonexistent_no_error(self, mock_cloud):
    mock_cloud.delete_file(None, "nonexistent.txt")
```

- [ ] **Step 11: 更新 test_get_hash_nonexistent_raises 测试（删除或改为测试 FileInfo）**

删除这个测试，因为 `get_file_hash` 已移除。

- [ ] **Step 12: 提交**

```bash
git add tests/test_local_mock_cloud.py
git commit -m "test: update LocalMockCloudStorage tests for new interface"
```

---

## Task 6: 验证测试通过

**Files:**
- Test: `tests/test_local_mock_cloud.py`, `tests/test_sync_engine.py`

- [ ] **Step 1: 运行 LocalMockCloudStorage 测试**

```bash
PYTHONPATH=src pytest tests/test_local_mock_cloud.py -v
```

- [ ] **Step 2: 运行 SyncEngine 测试**

```bash
PYTHONPATH=src pytest tests/test_sync_engine.py -v
```

- [ ] **Step 3: 运行集成测试**

```bash
PYTHONPATH=src pytest tests/test_integration.py -v
```

---

## 自检清单

1. **Spec 覆盖检查：**
   - [x] FileInfo 数据类新增
   - [x] CloudStorage ABC 方法签名更新
   - [x] list_files 返回 List[FileInfo]
   - [x] upload_file 返回 FileInfo
   - [x] download_file 增加 file_id 参数
   - [x] delete_file 增加 file_id 参数
   - [x] rename_file 增加 file_id 参数并返回 FileInfo
   - [x] 移除 get_file_hash 和 get_file_size
   - [x] BaiduBOS 实现更新
   - [x] LocalMockCloudStorage 实现更新
   - [x] SyncEngine 适配新接口
   - [x] 测试更新

2. **占位符检查：** 无 TBD/TODO/实现后续等占位符

3. **类型一致性检查：** FileInfo 字段名在所有文件中一致使用
