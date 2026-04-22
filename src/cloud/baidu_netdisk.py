import hashlib
import json
import logging
import os
import threading
import time
from typing import List, Optional

import requests

from cloud.base import CloudStorage, FileInfo

logger = logging.getLogger(__name__)

# 百度网盘开放平台 API base URL
PAN_BASE_URL = "https://pan.baidu.com"
PCS_BASE_URL = "https://c3.pcs.baidu.com"
DLINK_BASE_URL = "https://d.pcs.baidu.com"


class BaiduNetdisk(CloudStorage):
    """百度网盘开放平台 (xpan) 云存储实现

    使用 OAuth2.0 用户授权认证，支持自动 token 刷新
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        app_name: str = "cloud_file_sync"
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.app_name = app_name
        self._token_lock = threading.Lock()
        self._token_expires_at: Optional[float] = None

        # token 有效期默认 30 天（百度实际返回的是 2592000 秒）
        self._token_refresh_window = 300  # 提前 5 分钟刷新

    def _ensure_valid_token(self) -> None:
        """确保 access_token 有效，必要时自动刷新"""
        with self._token_lock:
            if self._token_expires_at and time.time() < (self._token_expires_at - self._token_refresh_window):
                return

            if not self.refresh_token:
                logger.warning("No refresh token available, token may be expired")
                return

            self._refresh_access_token()

    def _refresh_access_token(self) -> bool:
        """使用 refresh_token 刷新 access_token"""
        try:
            url = f"{PAN_BASE_URL}/oauth/2.0/token"
            params = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": os.environ.get("NETDISK_CLIENT_ID", ""),
                "client_secret": os.environ.get("NETDISK_CLIENT_SECRET", ""),
            }
            response = requests.get(url, params=params, timeout=30)
            data = response.json()

            if response.status_code != 200 or "access_token" not in data:
                logger.error(f"Failed to refresh token: {data}")
                return False

            self.access_token = data["access_token"]
            self.refresh_token = data.get("refresh_token", self.refresh_token)

            os.environ["NETDISK_ACCESS_TOKEN"] = self.access_token
            if data.get("refresh_token"):
                os.environ["NETDISK_REFRESH_TOKEN"] = data["refresh_token"]

            expires_in = data.get("expires_in", 2592000)
            self._token_expires_at = time.time() + expires_in

            logger.info("Successfully refreshed access token")
            return True

        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
        headers: Optional[dict] = None,
        stream: bool = False,
        **kwargs
    ):
        """封装 HTTP 请求，自动处理 401 刷新"""
        if headers is None:
            headers = {}

        for attempt in range(2):
            self._ensure_valid_token()

            if "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {self.access_token}"

            response = requests.request(
                method=method,
                url=url,
                params=params,
                data=data,
                files=files,
                headers=headers,
                stream=stream,
                timeout=kwargs.get("timeout", 300),
                **kwargs
            )

            if response.status_code == 401 and attempt == 0:
                logger.warning("Got 401, attempting token refresh")
                if self._refresh_access_token():
                    continue
            break

        response.raise_for_status()
        return response

    def _build_remote_path(self, remote_path: str) -> str:
        """构建完整的网盘路径

        百度网盘要求文件在 /apps/{app_name}/ 目录下
        """
        if remote_path.startswith("/apps/"):
            return remote_path
        return f"/apps/{self.app_name}{remote_path}"

    def _calc_md5(self, data: bytes) -> str:
        """计算数据的 MD5（32位小写）"""
        return hashlib.md5(data).hexdigest()

    def list_files(
        self,
        prefix: str = "",
        is_include_tmp: bool = False,
        recursive: bool = True,
        include_dirs: bool = False
    ) -> List[FileInfo]:
        """列出网盘文件

        API: GET /rest/2.0/xpan/file?method=list&dir=path
        """
        params = {
            "method": "list",
            "dir": self._build_remote_path(prefix),
            "by": "name",
            "order": "asc",
        }
        if recursive:
            params["recursion"] = 1

        response = self._request("GET", f"{PAN_BASE_URL}/rest/2.0/xpan/file", params=params)
        data = response.json()

        if data.get("errno") != 0:
            raise RuntimeError(f"List files failed: {data}")

        results = []
        for item in data.get("list", []):
            is_dir = item.get("isdir") == 1

            if is_dir:
                if include_dirs:
                    results.append(FileInfo(
                        file_id=str(item.get("fs_id")),
                        file_path=item.get("path"),
                        size=None,
                        file_hash=None,
                        hash_algo=None,
                        local_mtime=self._parse_time(item.get("server_mtime")),
                        isdir=True
                    ))
                continue

            filename = item.get("server_filename", "")
            if not is_include_tmp and filename.endswith(".tmp"):
                continue

            results.append(FileInfo(
                file_id=str(item.get("fs_id")),
                file_path=item.get("path"),
                size=int(item.get("size", 0)) if item.get("size") else None,
                file_hash=item.get("md5"),
                hash_algo="md5",
                local_mtime=self._parse_time(item.get("server_mtime")),
                isdir=False
            ))

        return results

    def _parse_time(self, timestr_or_int) -> Optional[int]:
        """解析网盘时间字符串或时间戳为 Unix timestamp"""
        if not timestr_or_int:
            return None
        try:
            if isinstance(timestr_or_int, int):
                return timestr_or_int
            return int(timestr_or_int)
        except (ValueError, TypeError):
            return None

    def upload_file(self, local_path: str, remote_path: str) -> FileInfo:
        """上传文件到网盘

        使用分片上传接口，三步流程：
        1. 预上传 (precreate) 获取 uploadid
        2. 分片上传 (superfile2) 每块数据
        3. 创建文件 (create) 完成上传
        """
        remote_path = self._build_remote_path(remote_path)
        local_filename = os.path.basename(local_path)
        file_size = os.path.getsize(local_path)

        # Step 1: 预上传
        block_list = []
        chunk_size = 4 * 1024 * 1024  # 4MB 分片

        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                block_list.append(self._calc_md5(chunk))

        params = {
            "method": "precreate",
            "path": remote_path,
            "size": file_size,
            "isdir": 0,
            "autoinit": 1,
            "block_list": json.dumps(block_list),
        }
        response = self._request("POST", f"{PAN_BASE_URL}/rest/2.0/xpan/file", params=params)
        pre_data = response.json()

        if pre_data.get("errno") != 0:
            raise RuntimeError(f"Preupload failed: {pre_data}")

        upload_id = pre_data.get("uploadid")
        returned_block_list = pre_data.get("block_list", [])

        # Step 2: 分片上传
        with open(local_path, "rb") as f:
            chunk_index = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                upload_params = {
                    "method": "upload",
                    "access_token": self.access_token,
                    "type": "tmpfile",
                    "path": remote_path,
                    "uploadid": upload_id,
                    "partseq": returned_block_list[chunk_index] if chunk_index < len(returned_block_list) else chunk_index,
                }

                files = {"file": (local_filename, chunk)}

                upload_response = requests.post(
                    f"{PCS_BASE_URL}/rest/2.0/pcs/superfile2",
                    params=upload_params,
                    files=files,
                    timeout=300
                )
                upload_response.raise_for_status()
                chunk_index += 1

        # Step 3: 创建文件
        create_params = {
            "method": "create",
            "access_token": self.access_token,
            "path": remote_path,
            "uploadid": upload_id,
            "block_list": json.dumps(block_list),
        }
        create_response = self._request("POST", f"{PAN_BASE_URL}/rest/2.0/xpan/file", params=create_params)
        create_data = create_response.json()

        if create_data.get("errno") != 0:
            raise RuntimeError(f"Create file failed: {create_data}")

        return FileInfo(
            file_id=remote_path,
            file_path=remote_path,
            size=file_size,
            file_hash=create_data.get("md5"),
            hash_algo="md5",
            local_mtime=int(os.path.getmtime(local_path)),
            isdir=False
        )

    def download_file(
        self,
        file_id: Optional[str],
        remote_path: str,
        local_path: str
    ) -> None:
        """下载网盘文件

        两步流程：
        1. 查询文件信息获取下载地址 dlink
        2. 使用 dlink 下载文件
        """
        remote_path = self._build_remote_path(remote_path)

        # Step 1: 获取文件信息（包括 dlink）
        meta_params = {
            "method": "meta",
            "access_token": self.access_token,
            "dlink": 1,
            "fsids": json.dumps([0]),  # 需要提供 fs_id，这里用 0 作为占位
        }

        # 先列出文件获取 fs_id
        list_params = {
            "method": "list",
            "dir": os.path.dirname(remote_path) or "/",
            "access_token": self.access_token,
        }
        list_response = self._request("GET", f"{PAN_BASE_URL}/rest/2.0/xpan/file", params=list_params)
        list_data = list_response.json()

        fs_id = None
        dlink = None

        if list_data.get("errno") == 0:
            for item in list_data.get("list", []):
                if item.get("path") == remote_path:
                    fs_id = item.get("fs_id")
                    break

        if not fs_id:
            raise RuntimeError(f"File not found: {remote_path}")

        # 获取 dlink
        meta_params["fsids"] = json.dumps([fs_id])
        meta_response = self._request("GET", f"{PAN_BASE_URL}/rest/2.0/xpan/file", params=meta_params)
        meta_data = meta_response.json()

        if meta_data.get("errno") != 0:
            raise RuntimeError(f"Get file meta failed: {meta_data}")

        info = meta_data.get("list", [{}])[0]
        dlink = info.get("dlink")

        if not dlink:
            raise RuntimeError(f"No dlink available for file: {remote_path}")

        # Step 2: 使用 dlink 下载
        dlink_url = f"{dlink}&access_token={self.access_token}"

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

        download_headers = {
            "User-Agent": "pan.baidu.com"
        }

        response = requests.get(dlink_url, headers=download_headers, stream=True, timeout=300)
        response.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    def delete_file(self, file_id: Optional[str], remote_path: str) -> None:
        """删除网盘文件

        API: POST /rest/2.0/xpan/file?method=filemanager&opera=delete
        """
        remote_path = self._build_remote_path(remote_path)

        params = {
            "method": "filemanager",
            "opera": "delete",
        }
        data = {
            "async": 1,
            "filelist": json.dumps([remote_path]),
        }

        response = self._request("POST", f"{PAN_BASE_URL}/rest/2.0/xpan/file", params=params, data=data)
        result = response.json()

        if result.get("errno") != 0:
            raise RuntimeError(f"Delete failed: {result}")

    def rename_file(
        self,
        file_id: Optional[str],
        old_path: str,
        new_path: str
    ) -> FileInfo:
        """重命名网盘文件

        API: POST /rest/2.0/xpan/file?method=filemanager&opera=rename
        """
        old_path = self._build_remote_path(old_path)
        new_path = self._build_remote_path(new_path)

        params = {
            "method": "filemanager",
            "opera": "rename",
        }
        data = {
            "async": 1,
            "filelist": json.dumps([{"path": old_path, "newname": os.path.basename(new_path)}]),
        }

        response = self._request("POST", f"{PAN_BASE_URL}/rest/2.0/xpan/file", params=params, data=data)
        result = response.json()

        if result.get("errno") != 0:
            raise RuntimeError(f"Rename failed: {result}")

        return FileInfo(
            file_id=new_path,
            file_path=new_path,
            size=None,
            file_hash=None,
            hash_algo=None,
            local_mtime=None,
            isdir=False
        )
