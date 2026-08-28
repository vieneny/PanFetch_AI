from __future__ import annotations

import json
import hashlib
from collections import deque
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import requests
import truststore

from panfetch_ai.core.cancellation import CancellationToken
from panfetch_ai.core.baidu_mcp import BaiduMcpClient
from panfetch_ai.core.config import ConfigStore
from panfetch_ai.core.models import RemoteItem


truststore.inject_into_ssl()

API_BASE = "https://pan.baidu.com"
PCS_BASE = "https://d.pcs.baidu.com"
USER_AGENT = "pan.baidu.com"
UPLOAD_CHUNK_SIZE = 4 * 1024 * 1024


class NetdiskError(RuntimeError):
    pass


def normalize_remote_path(path: str) -> str:
    value = (path or "/").strip()
    if not value.startswith("/") or "\\" in value:
        raise ValueError("网盘路径必须以 / 开头，并使用 / 作为分隔符")
    pure = PurePosixPath(value)
    if ".." in pure.parts:
        raise ValueError("网盘路径不能包含 ..")
    return str(pure).rstrip("/") or "/"


class BaiduNetdiskClient:
    def __init__(
        self,
        token: str | None = None,
        session: requests.Session | None = None,
        config_store: ConfigStore | None = None,
        cancellation: CancellationToken | None = None,
        mcp_client: BaiduMcpClient | None = None,
    ) -> None:
        self.config_store = config_store or ConfigStore()
        self.token = token or self.config_store.read_baidu_token()
        self.session = session or requests.Session()
        self.cancellation = cancellation
        self.mcp_client = mcp_client
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _check_cancelled(self) -> None:
        if self.cancellation is not None:
            self.cancellation.raise_if_cancelled()

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self._check_cancelled()
        try:
            response = self.session.get(
                f"{API_BASE}{path}",
                params={**params, "access_token": self.token, "openapi": "xpansdk"},
                timeout=(10, 60),
            )
        except requests.RequestException:
            self._check_cancelled()
            raise NetdiskError("无法连接百度网盘接口，请检查网络和系统证书") from None
        self._check_cancelled()
        return self._response_json(response)

    def _post_json(
        self,
        path: str,
        params: dict[str, Any],
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        base_url: str = API_BASE,
        timeout: tuple[int, int] = (10, 120),
    ) -> dict[str, Any]:
        self._check_cancelled()
        try:
            response = self.session.post(
                f"{base_url}{path}",
                params={**params, "access_token": self.token, "openapi": "xpansdk"},
                data=data,
                files=files,
                timeout=timeout,
            )
        except requests.RequestException:
            self._check_cancelled()
            raise NetdiskError("无法连接百度网盘接口，请检查网络和系统证书") from None
        self._check_cancelled()
        return self._response_json(response)

    @staticmethod
    def _response_json(response: Any) -> dict[str, Any]:
        if not response.ok:
            raise NetdiskError(f"百度网盘接口返回 HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise NetdiskError("百度网盘接口没有返回 JSON") from None
        errno = payload.get("errno", payload.get("error_code", 0))
        if errno not in (0, "0", None):
            message = payload.get("errmsg") or payload.get("error_msg") or "未知错误"
            raise NetdiskError(f"百度网盘接口错误 {errno}: {message}")
        return payload

    def account_info(self) -> dict[str, Any]:
        payload = self._get_json("/rest/2.0/xpan/nas", {"method": "uinfo"})
        allowed = ("baidu_name", "netdisk_name", "uk", "vip_type", "avatar_url")
        return {key: payload[key] for key in allowed if key in payload}

    def quota_info(self) -> dict[str, Any]:
        payload = self._get_json("/api/quota", {"checkexpire": 1, "checkfree": 1})
        allowed = ("total", "used", "free", "expire")
        return {key: payload[key] for key in allowed if key in payload}

    def share_available(self) -> bool:
        self._check_cancelled()
        available = (self.mcp_client or BaiduMcpClient(self.token)).share_available()
        self._check_cancelled()
        return available

    def create_share(self, remote_paths: list[str], period: int) -> dict[str, Any]:
        paths = list(dict.fromkeys(normalize_remote_path(path) for path in remote_paths))
        if not paths:
            raise ValueError("请至少选择一个需要分享的文件或文件夹")
        if "/" in paths:
            raise ValueError("不能直接分享整个网盘根目录，请选择根目录下的文件或文件夹")
        by_parent: dict[str, list[str]] = {}
        for path in paths:
            by_parent.setdefault(str(PurePosixPath(path).parent), []).append(path)
        fs_ids: list[int] = []
        for parent, expected_paths in by_parent.items():
            items = {item.path: item for item in self.list_directory(parent)}
            for path in expected_paths:
                item = items.get(path)
                if item is None or item.fs_id <= 0:
                    raise NetdiskError(f"找不到需要分享的网盘内容：{path}")
                fs_ids.append(item.fs_id)
        self._check_cancelled()
        payload = (self.mcp_client or BaiduMcpClient(self.token)).create_share(fs_ids, period)
        self._check_cancelled()
        return payload

    def avatar_bytes(self, avatar_url: str) -> bytes:
        if not avatar_url.startswith("https://"):
            return b""
        try:
            response = self.session.get(avatar_url, timeout=(10, 20))
        except requests.RequestException:
            return b""
        content = response.content if response.ok else b""
        return content if len(content) <= 2 * 1024 * 1024 else b""

    def list_directory(self, remote_dir: str = "/", limit: int = 0) -> list[RemoteItem]:
        directory = normalize_remote_path(remote_dir)
        offset = 0
        items: list[RemoteItem] = []
        while limit == 0 or len(items) < limit:
            page_size = 1000 if limit == 0 else min(1000, limit - len(items))
            payload = self._get_json(
                "/rest/2.0/xpan/file",
                {
                    "method": "list",
                    "dir": directory,
                    "start": str(offset),
                    "limit": page_size,
                    "order": "name",
                    "desc": 0,
                    "showempty": 1,
                },
            )
            batch = payload.get("list") or []
            items.extend(RemoteItem.from_api(item) for item in batch)
            offset += len(batch)
            has_more = bool(payload.get("has_more")) or len(batch) >= page_size
            if not batch or not has_more:
                break
        return _sort_items(items[:limit] if limit else items)

    def walk(
        self,
        remote_dir: str,
        max_depth: int = -1,
        limit: int = 0,
        progress: Callable[[str, int], None] | None = None,
    ) -> list[RemoteItem]:
        root = normalize_remote_path(remote_dir)
        pending: deque[tuple[str, int]] = deque([(root, 1)])
        items: list[RemoteItem] = []
        while pending and (limit == 0 or len(items) < limit):
            directory, depth = pending.popleft()
            children = self.list_directory(directory)
            for item in children:
                items.append(item)
                if item.is_dir and (max_depth == -1 or depth < max_depth):
                    pending.append((item.path, depth + 1))
                if limit and len(items) >= limit:
                    break
            if progress:
                progress(directory, len(items))
        return items

    def search(
        self,
        keyword: str,
        remote_dir: str = "/",
        recursive: bool = True,
        limit: int = 100,
        category: int = 0,
        file_only: bool = False,
        dir_only: bool = False,
    ) -> list[RemoteItem]:
        query = keyword.strip()
        if not query:
            raise ValueError("搜索关键词不能为空")
        if category not in range(0, 8):
            raise ValueError("搜索类型必须是 0 到 7")
        if file_only and dir_only:
            raise ValueError("仅文件与仅文件夹不能同时启用")
        directory = normalize_remote_path(remote_dir)
        target = min(max(limit, 1), 1000)
        page = 1
        items: list[RemoteItem] = []
        while len(items) < target:
            page_size = min(100, target - len(items))
            payload = self._get_json(
                "/rest/2.0/xpan/file",
                {
                    "method": "search",
                    "key": query,
                    "dir": directory,
                    "recursion": 1 if recursive else 0,
                    "page": page,
                    "num": page_size,
                    "category": category,
                },
            )
            batch = payload.get("list") or []
            converted = [RemoteItem.from_api(item) for item in batch]
            if category:
                converted = [item for item in converted if item.is_dir or item.category in {0, category}]
            if file_only:
                converted = [item for item in converted if not item.is_dir]
            elif dir_only:
                converted = [item for item in converted if item.is_dir]
            items.extend(converted)
            if not batch or not (bool(payload.get("has_more")) or len(batch) >= page_size):
                break
            page += 1
        return _sort_items(items[:target])

    def metadata(self, fs_ids: list[int], include_download_link: bool = False) -> list[dict[str, Any]]:
        if not fs_ids or len(fs_ids) > 10:
            raise ValueError("每次元数据查询必须包含 1 到 10 个文件 ID")
        payload = self._get_json(
            "/rest/2.0/xpan/multimedia",
            {
                "method": "filemetas",
                "fsids": json.dumps([int(value) for value in fs_ids], separators=(",", ":")),
                "dlink": 1 if include_download_link else 0,
                "thumb": 1,
            },
        )
        return list(payload.get("list") or [])

    def create_directory(self, remote_path: str) -> dict[str, Any]:
        path = normalize_remote_path(remote_path)
        if path == "/":
            return {"path": "/", "isdir": 1}
        parent = str(PurePosixPath(path).parent)
        if parent != path and parent != "/":
            self.ensure_directory(parent)
        return self._post_json(
            "/rest/2.0/xpan/file",
            {"method": "create"},
            {"path": path, "isdir": 1, "size": 0, "uploadid": "", "block_list": "[]", "rtype": 3},
        )

    def ensure_directory(self, remote_path: str) -> None:
        path = normalize_remote_path(remote_path)
        if path == "/":
            return
        parent = str(PurePosixPath(path).parent)
        if parent != "/":
            self.ensure_directory(parent)
        existing = next((item for item in self.list_directory(parent) if item.path == path), None)
        if existing is not None:
            if not existing.is_dir:
                raise NetdiskError(f"目标路径已存在同名文件：{path}")
            return
        self.create_directory(path)

    def move(self, source: str, destination: str) -> dict[str, Any]:
        return self._file_manager("move", source, destination=destination)

    def copy(self, source: str, destination: str) -> dict[str, Any]:
        return self._file_manager("copy", source, destination=destination)

    def rename(self, path: str, new_name: str) -> dict[str, Any]:
        if not new_name.strip() or any(char in new_name for char in "/\\") or new_name in {".", ".."}:
            raise ValueError("新名称只能是单个文件名或文件夹名")
        return self._file_manager("rename", path, new_name=new_name.strip())

    def _file_manager(
        self,
        operation: str,
        source: str,
        destination: str = "",
        new_name: str = "",
    ) -> dict[str, Any]:
        path = normalize_remote_path(source)
        if operation in {"move", "copy"}:
            target = normalize_remote_path(destination)
            file_entry = {
                "path": path,
                "dest": target,
                "newname": PurePosixPath(path).name,
                "ondup": "fail",
            }
        elif operation == "rename":
            file_entry = {"path": path, "newname": new_name}
        else:
            raise ValueError("不支持的文件管理操作")
        payload = self._post_json(
            "/rest/2.0/xpan/file",
            {"method": "filemanager", "opera": operation},
            {"async": 0, "filelist": json.dumps([file_entry], ensure_ascii=False, separators=(",", ":"))},
        )
        failures = [item for item in payload.get("info") or [] if item.get("errno") not in (0, "0", None)]
        if failures:
            first = failures[0]
            raise NetdiskError(f"百度网盘文件操作失败 {first.get('errno')}: {first.get('errmsg') or '未知错误'}")
        return payload

    def upload_path(
        self,
        local_path: str,
        remote_path: str,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        source = Path(local_path).expanduser().resolve()
        if not source.exists():
            raise ValueError(f"本地路径不存在：{source}")
        target = normalize_remote_path(remote_path)
        report = progress or (lambda _: None)
        if source.is_file():
            self.ensure_directory(str(PurePosixPath(target).parent))
            return [self.upload_file(source, target, report)]
        self.ensure_directory(target)
        files = sorted(item for item in source.rglob("*") if item.is_file())
        results: list[dict[str, Any]] = []
        for index, item in enumerate(files, 1):
            relative = item.relative_to(source).as_posix()
            remote_file = f"{target.rstrip('/')}/{relative}"
            self.ensure_directory(str(PurePosixPath(remote_file).parent))
            report({"stage": "upload", "path": str(item), "current": index, "total": len(files)})
            results.append(self.upload_file(item, remote_file, report))
        return results

    def upload_file(
        self,
        local_file: str | Path,
        remote_file: str,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        source = Path(local_file).resolve()
        if not source.is_file():
            raise ValueError(f"本地文件不存在：{source}")
        target = normalize_remote_path(remote_file)
        size = source.stat().st_size
        report = progress or (lambda _: None)
        hashes: list[str] = []
        with source.open("rb") as handle:
            while chunk := handle.read(UPLOAD_CHUNK_SIZE):
                hashes.append(hashlib.md5(chunk).hexdigest())
        if not hashes:
            hashes = [hashlib.md5(b"").hexdigest()]
        block_list = json.dumps(hashes, separators=(",", ":"))
        precreate = self._post_json(
            "/rest/2.0/xpan/file",
            {"method": "precreate"},
            {"path": target, "isdir": 0, "size": size, "autoinit": 1, "block_list": block_list, "rtype": 3},
        )
        upload_id = str(precreate.get("uploadid") or "")
        if not upload_id:
            raise NetdiskError("百度网盘预上传未返回 uploadid")
        with source.open("rb") as handle:
            for index in range(len(hashes)):
                chunk = handle.read(UPLOAD_CHUNK_SIZE)
                self._post_json(
                    "/rest/2.0/pcs/superfile2",
                    {"method": "upload", "path": target, "uploadid": upload_id, "partseq": index, "type": "tmpfile"},
                    files={"file": (source.name, chunk, "application/octet-stream")},
                    base_url=PCS_BASE,
                    timeout=(10, 300),
                )
                report({"stage": "chunk", "path": str(source), "current": index + 1, "total": len(hashes)})
        created = self._post_json(
            "/rest/2.0/xpan/file",
            {"method": "create"},
            {"path": target, "isdir": 0, "size": size, "uploadid": upload_id, "block_list": block_list, "rtype": 3},
        )
        return {"path": target, "size": size, "fs_id": created.get("fs_id")}


def _sort_items(items: list[RemoteItem]) -> list[RemoteItem]:
    return sorted(items, key=lambda item: (not item.is_dir, item.name.casefold()))
