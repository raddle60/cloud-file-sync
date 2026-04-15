# src/storage/sync_state.py
from typing import Dict, List, Optional, Tuple
from models.sync_pair import FileMeta

class LocalFileInfo:
    """本地文件信息"""
    def __init__(self, meta: FileMeta, cloud_name: str):
        self.meta = meta
        self.cloud_name = cloud_name
        self.deleted = False
        self.deleted_at: Optional[int] = None

class CloudMetaInfo:
    """云端meta信息"""
    def __init__(self, meta: FileMeta, cloud_name: str):
        self.meta = meta
        self.cloud_name = cloud_name

class SyncState:
    """本地同步状态管理（内存中）"""

    def __init__(self):
        # key: (local_root, relative_path) -> LocalFileInfo
        self._local_files: Dict[Tuple[str, str], LocalFileInfo] = {}
        # key: (remote_prefix, cloud_name) -> CloudMetaInfo
        self._cloud_metas: Dict[Tuple[str, str], CloudMetaInfo] = {}

    def add_file(self, local_root: str, remote_prefix: str, meta: FileMeta, cloud_name: str):
        """添加文件到状态"""
        local_key = (local_root, meta.relative_path)
        cloud_key = (remote_prefix, cloud_name)

        self._local_files[local_key] = LocalFileInfo(meta, cloud_name)
        self._cloud_metas[cloud_key] = CloudMetaInfo(meta, cloud_name)

    def has_local_file(self, local_root: str, relative_path: str) -> bool:
        key = (local_root, relative_path)
        info = self._local_files.get(key)
        return info is not None and not info.deleted

    def has_cloud_meta(self, remote_prefix: str, cloud_name: str) -> bool:
        key = (remote_prefix, cloud_name)
        return key in self._cloud_metas

    def get_local_file_info(self, local_root: str, relative_path: str) -> Optional[Dict]:
        key = (local_root, relative_path)
        info = self._local_files.get(key)
        if info is None:
            return None
        return {
            "meta": info.meta,
            "cloud_name": info.cloud_name,
            "deleted": info.deleted,
            "deleted_at": info.deleted_at
        }

    def get_cloud_meta(self, remote_prefix: str, cloud_name: str) -> Optional[FileMeta]:
        key = (remote_prefix, cloud_name)
        info = self._cloud_metas.get(key)
        return info.meta if info else None

    def mark_local_deleted(self, local_root: str, relative_path: str, deleted_at: int):
        """标记本地文件已删除"""
        key = (local_root, relative_path)
        if key in self._local_files:
            self._local_files[key].deleted = True
            self._local_files[key].deleted_at = deleted_at

    def remove_cloud_meta(self, remote_prefix: str, cloud_name: str):
        """移除云端meta记录"""
        key = (remote_prefix, cloud_name)
        self._cloud_metas.pop(key, None)

    def get_files_needing_sync(self, local_root: str, remote_prefix: str) -> List[Dict]:
        """获取需要同步的文件列表"""
        result = []

        for (lr, rp), info in self._local_files.items():
            if lr != local_root:
                continue
            if info.deleted:
                result.append({
                    "type": "delete_local",
                    "relative_path": rp,
                    "cloud_name": info.cloud_name
                })
            else:
                result.append({
                    "type": "upload",
                    "relative_path": rp,
                    "meta": info.meta,
                    "cloud_name": info.cloud_name
                })

        return result
