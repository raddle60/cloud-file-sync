# CloudStorage 基类方法改造设计

## 背景

之前的 `CloudStorage` 基类方法与云端接口不匹配，需要改造以支持：
1. 文件元信息标准化
2. 云端文件标识支持
3. 云端能力适配（不同云端支持不同特性）

## 设计

### 1. FileInfo 数据类

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class FileInfo:
    file_id: Optional[str]     # 云端唯一标识，可能为 None（某些云端无此概念）
    file_path: str              # 云端文件路径
    size: Optional[int]         # 文件大小，可能为 None
    file_hash: Optional[str]    # 文件 hash，可能为 None
    hash_algo: Optional[str]     # hash 算法，默认 None
    local_mtime: Optional[int]  # 最后修改时间（Unix timestamp），可能为 None
    isdir: bool                 # 是否为目录
```

**字段说明：**
- `file_id`：云端返回的唯一标识，可能为 `None`（某些云端不支持或新上传文件尚无）
- `file_path`：云端文件路径，必填
- `size`、`file_hash`、`hash_algo`、`local_mtime`：可能为 `None`，表示云端不支持或未提供
- `isdir`：区分文件还是目录

### 2. CloudStorage ABC 方法签名

```python
class CloudStorage(ABC):
    @abstractmethod
    def list_files(
        self,
        prefix: str = "",
        is_include_tmp: bool = False,
        recursive: bool = True,
        include_dirs: bool = False
    ) -> List[FileInfo]:
        """
        列出云端文件

        Args:
            prefix: 路径前缀过滤
            is_include_tmp: 是否包含 .tmp 临时文件
            recursive: 是否递归查询子目录，默认 True
            include_dirs: 是否返回目录类型，默认 False（只返回文件）

        Returns:
            FileInfo 列表
        """
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> FileInfo:
        """上传文件到云端，返回新文件的 FileInfo"""
        pass

    @abstractmethod
    def download_file(
        self,
        file_id: Optional[str],
        remote_path: str,
        local_path: str
    ) -> None:
        """
        下载文件到本地

        Args:
            file_id: 云端文件标识（实现类可根据云端能力选择使用 file_id 或 remote_path）
            remote_path: 云端文件路径
            local_path: 本地目标路径
        """
        pass

    @abstractmethod
    def delete_file(self, file_id: Optional[str], remote_path: str) -> None:
        """
        删除云端文件

        Args:
            file_id: 云端文件标识（实现类可根据云端能力选择使用）
            remote_path: 云端文件路径
        """
        pass

    @abstractmethod
    def rename_file(
        self,
        file_id: Optional[str],
        old_path: str,
        new_path: str
    ) -> FileInfo:
        """
        重命名云端文件

        Args:
            file_id: 云端文件标识（实现类可根据云端能力选择使用）
            old_path: 原路径
            new_path: 新路径

        Returns:
            重命名后的 FileInfo
        """
        pass
```

### 3. 移除的方法

- `get_file_hash(remote_path: str) -> str`
- `get_file_size(remote_path: str) -> int`

这两个方法的功能已由 `FileInfo` 的 `size` 和 `file_hash` 字段替代。

### 4. 实现类适配说明

- **BaiduBOS**：可忽略 `file_id` 参数，直接使用 `remote_path`（BOS 以路径为键）
- **其他云端**：可根据云端能力决定是否使用 `file_id`（如 S3 的 ETag）

## 实现计划

1. 新增 `FileInfo` 数据类到 `cloud/base.py`
2. 修改 `CloudStorage` ABC 方法签名
3. 更新 `BaiduBOS` 实现
4. 更新 `LocalMockCloudStorage` 实现
5. 更新 `SyncEngine` 调用以适配新接口
6. 移除 `get_file_hash` 和 `get_file_size` 调用
