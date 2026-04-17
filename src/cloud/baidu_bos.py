import os
from typing import List, Optional
from baidubce.services.bos.bos_client import BosClient, bce_client_configuration
from baidubce.auth.bce_credentials import BceCredentials
from cloud.base import CloudStorage, FileInfo

class BaiduBOS(CloudStorage):
    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str
    ):
        credentials = BceCredentials(access_key_id, access_key_secret)
        config = bce_client_configuration.BceClientConfiguration(credentials, endpoint)
        self.bos_client = BosClient(config)
        self.bucket_name = bucket_name

    def list_files(
        self,
        prefix: str = "",
        is_include_tmp: bool = False,
        recursive: bool = True,
        include_dirs: bool = False
    ) -> List[FileInfo]:
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

    def download_file(
        self,
        file_id: Optional[str],
        remote_path: str,
        local_path: str
    ) -> None:
        # file_id 参数 BaiduBOS 不使用，直接用 remote_path
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        self.bos_client.get_object_to_file(self.bucket_name, remote_path, local_path)

    def delete_file(self, file_id: Optional[str], remote_path: str) -> None:
        # file_id 参数 BaiduBOS 不使用，直接用 remote_path
        self.bos_client.delete_object(self.bucket_name, remote_path)

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
