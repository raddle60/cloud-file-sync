import os
import time
from typing import Tuple
from models.sync_pair import FileMeta

class ConflictResolver:
    def generate_conflict_name(self, original_path: str, timestamp: int = None) -> str:
        """生成冲突文件名"""
        if timestamp is None:
            timestamp = int(time.time())

        dirname = os.path.dirname(original_path)
        basename = os.path.basename(original_path)

        if '.' in basename:
            parts = basename.rsplit('.', 1)
            name, ext = parts[0], '.' + parts[1]
            new_name = f"{name}.conflict-{timestamp}{ext}"
        else:
            new_name = f"{basename}.conflict-{timestamp}"

        if dirname:
            return os.path.join(dirname, new_name)
        return new_name

    def generate_cloud_conflict_name(self, cloud_name: str, timestamp: int = None) -> str:
        """生成云端冲突文件名"""
        if timestamp is None:
            timestamp = int(time.time())
        return f"{cloud_name}.conflict-{timestamp}"

    def resolve_local_conflict(self, file_path: str) -> str:
        """解决本地文件冲突，重命名旧文件"""
        if not os.path.exists(file_path):
            return file_path

        timestamp = int(time.time())
        new_name = self.generate_conflict_name(file_path, timestamp)

        os.rename(file_path, new_name)
        return new_name

    def decide_winner(self, local_meta: FileMeta, cloud_meta: FileMeta) -> str:
        """根据时间戳判断新旧，返回 'local' 或 'cloud'"""
        if cloud_meta.last_modified > local_meta.last_modified:
            return "cloud"
        elif local_meta.last_modified > cloud_meta.last_modified:
            return "local"
        else:
            # 时间戳相同，按sha256判断
            if cloud_meta.sha256 > local_meta.sha256:
                return "cloud"
            return "local"

    def handle_conflict(
        self,
        local_path: str,
        cloud_name: str,
        local_meta: FileMeta,
        cloud_meta: FileMeta
    ) -> Tuple[str, str]:
        """
        处理冲突，返回 (local_conflict_name, cloud_conflict_name)
        """
        timestamp = int(time.time())
        winner = self.decide_winner(local_meta, cloud_meta)

        if winner == "local":
            # 本地更新，云端旧版本需要重命名
            cloud_conflict_name = self.generate_cloud_conflict_name(cloud_name, timestamp)
            return None, cloud_conflict_name
        else:
            # 云端更新，本地旧版本需要重命名
            local_conflict_name = self.generate_conflict_name(local_path, timestamp)
            os.rename(local_path, local_conflict_name)
            return local_conflict_name, None
