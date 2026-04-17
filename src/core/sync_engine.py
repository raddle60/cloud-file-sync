import os
import time
import hashlib
import shutil
import logging
from typing import Optional, Tuple, Dict, List
from models.sync_pair import SyncPair, FileMeta
from storage.sync_state import SyncState
from core.crypto import CryptoManager, derive_key
from core.conflict_resolver import ConflictResolver
from meta.meta_manager import MetaManager
from cloud.base import CloudStorage
from utils.path_util import PathUtil

logger = logging.getLogger(__name__)


class SyncEngine:
    def __init__(
            self,
            sync_pair: SyncPair,
            state: SyncState,
            cloud_storage: CloudStorage,
            crypto: Optional[CryptoManager],
            config_key: str
    ):
        self.sync_pair = sync_pair
        self.state = state
        self.cloud_storage = cloud_storage
        self.crypto = crypto
        self.config_key = config_key
        self.conflict_resolver = ConflictResolver()
        self.meta_manager = MetaManager(
            encryption_enabled=sync_pair.encryption_enabled,
            crypto=crypto
        )
        self._local_metas: Dict[str, FileMeta] = {}  # 本地文件meta信息，key为relative_path

    def get_cloud_name(self, filename: str) -> str:
        """生成云端文件名"""
        if self.sync_pair.encryption_enabled:
            return hashlib.sha256(filename.encode()).hexdigest()
        return filename

    def get_cloud_path(self, relative_path: str) -> str:
        """获取云端完整路径"""
        remote = PathUtil.normalize_path(self.sync_pair.remote)
        rel = PathUtil.normalize_path(relative_path).lstrip('/')
        return PathUtil.normalize_path(f"{remote}/{rel}")

    def get_local_path(self, relative_path: str) -> str:
        """获取本地完整路径"""
        local = PathUtil.normalize_path(self.sync_pair.local)
        rel = PathUtil.normalize_path(relative_path).lstrip('/')
        if rel:
            return PathUtil.join(local, rel)
        return PathUtil.normalize_path(local)

    def scan_local_files(self):
        """扫描本地文件"""
        if not os.path.exists(self.sync_pair.local):
            return

        for dirpath, dirnames, filenames in os.walk(self.sync_pair.local):
            for filename in filenames:
                # 跳过 .tmp 文件
                if filename.endswith('.tmp'):
                    continue

                full_path = PathUtil.join(dirpath, filename)
                relative_path = PathUtil.normalize_path(os.path.relpath(full_path, self.sync_pair.local)).lstrip(r"\/")

                stat = os.stat(full_path)
                sha256 = self._calc_sha256(full_path)

                meta = FileMeta(
                    original_filename=filename,
                    size=stat.st_size,
                    last_modified=int(stat.st_mtime),
                    sha256=sha256,
                    relative_path=relative_path
                )

                cloud_name = self.get_cloud_name(filename)
                self.state.add_file(
                    self.sync_pair.local,
                    self.sync_pair.remote,
                    meta,
                    cloud_name
                )
                # 更新本地meta
                self._local_metas[relative_path] = meta

    def _calc_sha256(self, file_path: str) -> str:
        """计算文件SHA256"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _calc_file_meta(self, file_path: str, filename: str, relative_path: str) -> FileMeta:
        """从文件计算meta信息"""
        stat = os.stat(file_path)
        sha256 = self._calc_sha256(file_path)
        return FileMeta(
            original_filename=filename,
            size=stat.st_size,
            last_modified=int(stat.st_mtime),
            sha256=sha256,
            relative_path=relative_path
        )

    def _check_local_unfinished_tmp(self, relative_path: str) -> bool:
        """
        检查本地是否存在未完成的tmp文件
        如果本地存在 xxx.tmp 但对应的 xxx 文件正在被同步，说明有未完成的操作
        返回 True 表示检测到未完成的tmp文件，应跳过上传
        """
        tmp_path = self.get_local_path(relative_path + '.tmp')
        if os.path.exists(tmp_path):
            logger.error(f"[ERROR] Sync interrupted: local file has unfinished tmp: {relative_path}.tmp")
            return True
        return False

    def _check_cloud_unfinished_tmp(self, cloud_name: str) -> bool:
        """
        检查云端是否存在未完成的tmp文件
        如果云端存在 xxx.tmp 但对应的 xxx 文件正在被下载，说明有未完成的操作
        返回 True 表示检测到未完成的tmp文件，应跳过下载
        """
        cloud_tmp_path = cloud_name + '.tmp'
        cloud_files = self.cloud_storage.list_files(self.sync_pair.remote, is_include_tmp=True)
        for file_info in cloud_files:
            # 获取文件名（不含路径）
            fname = file_info.file_path.split('/')[-1]
            if fname == cloud_tmp_path or file_info.file_path == cloud_tmp_path:
                logger.error(f"[ERROR] Sync interrupted: cloud file has unfinished tmp: {cloud_name}.tmp")
                return True
        return False

    def full_sync(self):
        """执行全量同步"""
        # 1. 扫描本地文件
        self.scan_local_files()

        # 2. 获取云端文件列表（过滤掉 .tmp 文件）
        cloud_files = self.cloud_storage.list_files(self.sync_pair.remote)

        # 3. 解析云端meta文件，保存到内存
        cloud_metas = {}
        for file_info in cloud_files:
            if not file_info.file_path.endswith('.meta.json'):
                try:
                    cloud_path = PathUtil.normalize_path(file_info.file_path)
                    meta = self._download_and_read_meta(cloud_path + ".meta.json")
                    cloud_metas[cloud_path] = meta
                except Exception as e:
                    logger.error(f"[ERROR] Failed to parse cloud meta: {file_info.file_path} , exception: {e}")
                    continue

        # 4. 全量对比和同步
        # 遍历云端meta，检查是否需要下载到本地
        for cloud_name, meta in cloud_metas.items():
            local_path = self.get_local_path(meta.relative_path)

            # 检查云端是否有未完成的 tmp 文件
            if self._check_cloud_unfinished_tmp(cloud_name):
                continue

            # 检查本地是否存在
            if not os.path.exists(local_path):
                # 本地不存在，下载
                self.download_from_cloud(cloud_name, meta)
            else:
                # 本地存在，比较sha256
                local_sha256 = self._calc_sha256(local_path)
                if local_sha256 != meta.sha256:
                    # 内容不同，按时间戳判断
                    local_mtime = int(os.stat(local_path).st_mtime)
                    if meta.last_modified > local_mtime:
                        # 云端更新，下载
                        self.download_from_cloud(cloud_name, meta)
                    elif local_mtime > meta.last_modified:
                        # 本地更新，上传
                        self._upload_file_and_meta(local_path, meta.relative_path, cloud_name)

        # 6. 对比并上传本地有而云端没有的文件
        for (local_root, relative_path), info in self.state._local_files.items():
            if info.deleted:
                continue
            cloud_name = info.cloud_name
            cloud_path = self.get_cloud_path(relative_path)

            # 检查本地是否有未完成的 tmp 文件
            if self._check_local_unfinished_tmp(relative_path):
                continue

            # 检查云端是否已有该文件（通过实际云端列表）
            cloud_exists = any(f.file_path.lstrip(r"\/") == relative_path.lstrip(r"\/") for f in cloud_files)
            if not cloud_exists:
                # 上传文件
                local_path = self.get_local_path(relative_path)
                self._upload_file_and_meta(local_path, relative_path, cloud_name)

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
        cloud_path = cloud_name  # cloud_name already includes the remote path

        # 4. 原子下载
        self.atomic_download(cloud_path, local_path, meta.sha256)

        # 5. 从下载的文件重新生成meta
        downloaded_meta = self._calc_file_meta(local_path, os.path.basename(local_path), relative_path)

        # 6. 更新本地状态
        self.state.add_file(self.sync_pair.local, self.sync_pair.remote, downloaded_meta, cloud_name)
        # 7. 更新本地文件meta
        self._local_metas[relative_path] = downloaded_meta

    def atomic_upload(self, local_path: str, cloud_path: str, cloud_name: str):
        tmp_name = f"{cloud_name}.tmp"
        tmp_path = cloud_path + ".tmp"

        # 1. 上传到tmp
        self.cloud_storage.upload_file(local_path, tmp_path)

        # 2. 验证（优先hash，其次大小）
        # 获取云端文件信息进行验证
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

        # 3. 原子替换
        if verified:
            self.cloud_storage.delete_file(None, cloud_path)
            self.cloud_storage.rename_file(None, tmp_path, cloud_path)
        else:
            self.cloud_storage.delete_file(None, tmp_path)
            raise ValueError(f"Upload verification failed for {cloud_path}")

    def atomic_download(self, cloud_path: str, local_path: str, expected_sha256: str):
        """原子下载文件到本地"""
        tmp_path = local_path + ".tmp"

        # 1. 下载到tmp
        self.cloud_storage.download_file(None, cloud_path, tmp_path)

        # 2. 验证hash
        if self.sync_pair.encryption_enabled and self.crypto:
            # 解密后再验证
            decrypted_tmp = tmp_path + ".dec"
            self.crypto.decrypt_file(tmp_path, decrypted_tmp)
            sha256 = self._calc_sha256(decrypted_tmp)
            os.unlink(decrypted_tmp)
        else:
            sha256 = self._calc_sha256(tmp_path)

        # 3. 原子替换
        if sha256 == expected_sha256:
            if os.path.exists(local_path):
                os.unlink(local_path)
            os.rename(tmp_path, local_path)
        else:
            os.unlink(tmp_path)
            raise ValueError(f"Download verification failed for {local_path}")

    def _get_cloud_meta(self, relative_path: str) -> Optional[FileMeta]:
        """从云端获取指定文件的meta信息"""
        meta_path = relative_path + ".meta.json"
        try:
            return self._download_and_read_meta(meta_path)
        except Exception as e:
            logger.error(f"Failed to get meta for {relative_path}: {e}")
            return None

    def _download_and_read_meta(self, meta_path: str) -> FileMeta:
        """下载并解析meta文件"""
        import tempfile
        import os

        # 从meta_path推导relative_path
        relative_path = meta_path
        if meta_path.startswith(self.sync_pair.remote):
            relative_path = meta_path[len(self.sync_pair.remote):]
        relative_path = relative_path.lstrip(r"\/")

        # 去掉 .meta.json 后缀得到 relative_path
        if relative_path.endswith('.meta.json'):
            relative_path = relative_path[:-len('.meta.json')]

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            full_meta_path = PathUtil.join(self.sync_pair.remote, meta_path)
            self.cloud_storage.download_file(None, full_meta_path, tmp_path)

            if self.sync_pair.encryption_enabled and self.crypto:
                decrypted_tmp = tmp_path + ".dec"
                self.crypto.decrypt_file(tmp_path, decrypted_tmp)
                os.unlink(tmp_path)
                tmp_path = decrypted_tmp

            meta = self.meta_manager.read_meta(tmp_path)
            meta.relative_path = relative_path
            return meta
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def check_cloud_changes(self) -> List[Dict]:
        """
        检查云端变化，返回有变化的文件列表
        返回格式: [{"type": "new"|"modified"|"deleted", "cloud_name": str, "meta": FileMeta}]
        """
        # 1. 获取当前云端所有文件（过滤掉 .tmp 文件）
        cloud_files = self.cloud_storage.list_files(self.sync_pair.remote)
        cloud_file_paths = [f.file_path for f in cloud_files if not f.file_path.endswith('.tmp')]

        # 2. 解析meta文件
        current_metas: Dict[str, FileMeta] = {}
        for file_path in cloud_file_paths:
            if not file_path.endswith('.meta.json'):
                try:
                    cloud_path = PathUtil.normalize_path(file_path)
                    meta = self._download_and_read_meta(cloud_path + ".meta.json")
                    current_metas[cloud_path] = meta
                except Exception as e:
                    logger.error(f"check_cloud_changes Failed to parse meta for {file_path}: {e}")
                    continue

        changes: List[Dict] = []

        # 3. 与本地meta对比
        for cloud_name, meta in current_metas.items():
            # 检查云端是否有未完成的 tmp 文件
            if self._check_cloud_unfinished_tmp(cloud_name):
                continue

            local_meta = self._local_metas.get(meta.relative_path)
            if local_meta is None:
                # 本地没有，视为新增
                changes.append({"type": "new", "cloud_name": cloud_name, "meta": meta})
            elif local_meta.sha256 != meta.sha256:
                # 内容不同
                if meta.last_modified > local_meta.last_modified:
                    changes.append({"type": "modified", "cloud_name": cloud_name, "meta": meta})

        # 注：删除检测需要缓存云端状态，暂不支持

        return changes

    def incremental_sync(self, changed_files: List[str]):
        """
        增量同步变更的文件列表

        Args:
            changed_files: 变更文件的绝对路径列表
        """
        import time
        from datetime import datetime

        for file_path in changed_files:
            # 跳过 .tmp 文件
            if file_path.endswith('.tmp'):
                continue

            # 计算 relative_path
            relative_path = os.path.relpath(file_path, self.sync_pair.local)
            relative_path = PathUtil.normalize_path(relative_path)
            if not os.path.exists(file_path):
                # 文件已删除，标记删除状态
                self.state.mark_local_deleted(
                    self.sync_pair.local,
                    relative_path,
                    int(time.time())
                )
                # 获取本地meta用于后续比较（需要在移除前获取）
                local_meta = self._local_metas.get(relative_path)
                # 从本地meta中移除
                self._local_metas.pop(relative_path, None)
                # 检查云端是否有该文件（通过meta文件），满足条件则删除云端文件（保留meta）
                cloud_meta = self._get_cloud_meta(relative_path)
                if cloud_meta is not None and local_meta is not None:
                    # 只有sha256相同且本地时间>=云端时间才删除
                    if local_meta.sha256 == cloud_meta.sha256 and local_meta.last_modified >= cloud_meta.last_modified:
                        cloud_path = self.get_cloud_path(relative_path)
                        # 删除云端文件（meta文件永不删除）
                        self.cloud_storage.delete_file(None, cloud_path)
                        logger.info(f"[INFO] Deleted cloud file: {cloud_path}")
            else:
                # 文件新增或修改
                stat = os.stat(file_path)
                local_sha256 = self._calc_sha256(file_path)
                local_mtime = int(stat.st_mtime)
                cloud_name = self.get_cloud_name(os.path.basename(file_path))

                # 检查本地是否有未完成的 tmp 文件
                if self._check_local_unfinished_tmp(relative_path):
                    continue

                # 检查云端是否有对应的 meta 文件
                cloud_meta = self._get_cloud_meta(relative_path)

                if cloud_meta is None:
                    # 云端没有该文件，直接上传
                    self._upload_file_and_meta(file_path, relative_path, cloud_name)
                else:
                    # 云端有该文件，比较时间戳
                    if local_mtime > cloud_meta.last_modified:
                        # 本地更新，上传覆盖
                        self._upload_file_and_meta(file_path, relative_path, cloud_name)
                    elif local_mtime < cloud_meta.last_modified:
                        # 云端更新，冲突处理
                        self._handle_conflict(file_path, relative_path, cloud_name, cloud_meta, local_sha256,
                                              local_mtime)
                    else:
                        # 时间戳相同但仍触发变更，说明内容不同，也是冲突
                        if local_sha256 != cloud_meta.sha256:
                            self._handle_conflict(file_path, relative_path, cloud_name, cloud_meta, local_sha256,
                                                  local_mtime)

    def _handle_conflict(self, local_path: str, relative_path: str, cloud_name: str,
                         cloud_meta: 'FileMeta', local_sha256: str, local_mtime: int):
        """
        处理文件冲突

        Args:
            local_path: 本地文件路径
            relative_path: 相对路径
            cloud_name: 云端文件名
            cloud_meta: 云端meta信息
            local_sha256: 本地文件sha256
            local_mtime: 本地文件最后修改时间
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        local_filename = os.path.basename(local_path)
        name, ext = os.path.splitext(local_filename)

        if cloud_meta.sha256 == local_sha256:
            # 内容相同，只是时间戳记录误差，忽略
            logger.info(f"[INFO] File content same, ignoring timestamp difference: {local_path}")
            return

        # 本地文件重命名
        conflict_local_name = f"{name}.conflict-{timestamp}{ext}"
        conflict_local_path = PathUtil.join(os.path.dirname(local_path), conflict_local_name)
        os.rename(local_path, conflict_local_path)
        logger.info(f"[INFO] Renamed local file to: {conflict_local_name}")

        # 下载云端文件到本地原位置
        cloud_path = self.get_cloud_path(relative_path)
        self.download_from_cloud(cloud_name, cloud_meta)
        logger.info(f"[INFO] Downloaded cloud file to: {local_path}")

        # 上传重命名后的本地文件到云端
        cloud_conflict_name = cloud_name + f".conflict-{timestamp}"
        self._upload_file_and_meta(conflict_local_path, relative_path, cloud_conflict_name)
        logger.info(f"[INFO] Uploaded conflict file to cloud: {cloud_conflict_name}")

    def _upload_file_and_meta(self, file_path: str, relative_path: str, cloud_name: str):
        """
        上传文件及对应的meta到云端

        Args:
            file_path: 本地文件路径
            relative_path: 相对路径
            cloud_name: 云端文件名
        """
        # 检查云端是否有未完成的tmp文件
        if self._check_cloud_unfinished_tmp(cloud_name):
            logger.info(f"[INFO] Cloud has unfinished tmp file, skipping: {cloud_name}")
            return

        cloud_path = self.get_cloud_path(relative_path)

        # 从文件重新生成meta
        meta = self._calc_file_meta(file_path, os.path.basename(file_path), relative_path)

        # 更新状态
        self.state.add_file(self.sync_pair.local, self.sync_pair.remote, meta, cloud_name)
        # 更新本地文件meta
        self._local_metas[relative_path] = meta

        # 上传文件
        if self.sync_pair.encryption_enabled and self.crypto:
            encrypted_cloud_path = cloud_path
            tmp_encrypted = file_path + ".enc"
            self.crypto.encrypt_file(file_path, tmp_encrypted)
            self.atomic_upload(tmp_encrypted, encrypted_cloud_path, cloud_name)
            os.unlink(tmp_encrypted)

            # 上传meta
            meta_path = file_path + ".meta.json"
            self.meta_manager.write_meta(meta_path, meta)
            self.atomic_upload(meta_path, encrypted_cloud_path + ".meta.json", cloud_name + ".meta.json")
            os.unlink(meta_path)
        else:
            self.atomic_upload(file_path, cloud_path, cloud_name)
            # 上传meta
            meta_path = file_path + ".meta.json"
            self.meta_manager.write_meta(meta_path, meta)
            self.atomic_upload(meta_path, cloud_path + ".meta.json", cloud_name + ".meta.json")
            os.unlink(meta_path)

        logger.info(f"[INFO] Uploaded: {cloud_path}")
