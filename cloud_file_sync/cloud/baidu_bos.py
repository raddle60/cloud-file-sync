import os
from typing import List
from baidu.bce.bos import BosClient
from baidu.bce.auth import Credentials, BceCredentials
from cloud_file_sync.cloud.base import CloudStorage

class BaiduBOS(CloudStorage):
    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str
    ):
        credentials = BceCredentials(access_key_id, access_key_secret)
        self.bos_client = BosClient(credentials, endpoint)
        self.bucket_name = bucket_name

    def list_files(self, prefix: str = "") -> List[str]:
        response = self.bos_client.list_objects(self.bucket_name, prefix=prefix)
        contents = response.get('contents', [])
        return [item['key'] for item in contents]

    def download_file(self, remote_path: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
        self.bos_client.get_object_to_file(self.bucket_name, remote_path, local_path)

    def upload_file(self, local_path: str, remote_path: str) -> None:
        self.bos_client.put_object_from_file(
            self.bucket_name, remote_path, local_path
        )

    def delete_file(self, remote_path: str) -> None:
        self.bos_client.delete_object(self.bucket_name, remote_path)

    def rename_file(self, old_path: str, new_path: str) -> None:
        self.bos_client.copy_object(
            self.bucket_name, new_path,
            self.bucket_name, old_path
        )
        self.bos_client.delete_object(self.bucket_name, old_path)

    def get_file_hash(self, remote_path: str) -> str:
        response = self.bos_client.get_object_metadata(self.bucket_name, remote_path)
        return response.metadata.get('x-bce-content-sha256', '')

    def get_file_size(self, remote_path: str) -> int:
        response = self.bos_client.get_object_metadata(self.bucket_name, remote_path)
        return int(response.metadata.get('Content-Length', 0))