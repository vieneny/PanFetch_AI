from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import requests

from panfetch_ai.core.models import DownloadResult, RemoteItem, SelectionPlan
from panfetch_ai.core.netdisk import BaiduNetdiskClient, NetdiskError, USER_AGENT


WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class DownloadControl:
    def __init__(self) -> None:
        self._running = threading.Event()
        self._running.set()
        self._cancelled = threading.Event()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def cancel(self) -> None:
        self._cancelled.set()
        self._running.set()

    def wait(self) -> bool:
        self._running.wait()
        return not self._cancelled.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()


class DownloadManager:
    def __init__(self, client: BaiduNetdiskClient, concurrency: int = 5) -> None:
        self.client = client
        self.concurrency = max(1, min(concurrency, 10))

    def download(
        self,
        items: list[RemoteItem],
        plan: SelectionPlan,
        progress: Callable[[int, int, DownloadResult], None] | None = None,
        control: DownloadControl | None = None,
    ) -> list[DownloadResult]:
        control = control or DownloadControl()
        root = Path(plan.destination).expanduser()
        if not root.is_absolute():
            raise ValueError("下载目标必须是绝对路径")
        root.mkdir(parents=True, exist_ok=True)
        files = [item for item in items if not item.is_dir]
        results: list[DownloadResult] = []
        completed = 0

        for id_batch in _batched([item.fs_id for item in files], 10):
            if not control.wait():
                break
            metadata = self.client.metadata(id_batch, include_download_link=True)
            metadata_by_id = {int(item.get("fs_id", item.get("fsid", 0))): item for item in metadata}
            source_by_id = {item.fs_id: item for item in files if item.fs_id in id_batch}
            workers = min(self.concurrency, len(id_batch))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        self._download_one_with_retry,
                        source_by_id[fs_id],
                        metadata_by_id.get(fs_id, {}),
                        root,
                        plan,
                        control,
                    ): fs_id
                    for fs_id in id_batch
                    if fs_id in source_by_id
                }
                for future in as_completed(futures):
                    fs_id = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        source = source_by_id[fs_id]
                        result = DownloadResult(fs_id, source.path, "", "failed", error=str(exc))
                    results.append(result)
                    completed += 1
                    if progress:
                        progress(completed, len(files), result)
            if control.cancelled:
                break

        self.write_manifest(root, plan, results)
        return results

    def _download_one_with_retry(
        self,
        source: RemoteItem,
        metadata: dict[str, Any],
        root: Path,
        plan: SelectionPlan,
        control: DownloadControl,
    ) -> DownloadResult:
        last_error = "未知错误"
        for attempt in range(1, 4):
            if not control.wait():
                return DownloadResult(source.fs_id, source.path, "", "cancelled")
            try:
                return self._download_one(source, metadata, root, plan)
            except requests.RequestException:
                last_error = "文件网络请求失败"
                if attempt < 3:
                    time.sleep(2 ** (attempt - 1))
            except (OSError, NetdiskError, ValueError) as exc:
                last_error = str(exc)
                if attempt < 3:
                    time.sleep(2 ** (attempt - 1))
        return DownloadResult(source.fs_id, source.path, "", "failed", error=last_error)

    def _download_one(
        self,
        source: RemoteItem,
        metadata: dict[str, Any],
        root: Path,
        plan: SelectionPlan,
    ) -> DownloadResult:
        dlink = str(metadata.get("dlink") or "")
        parsed = urlparse(dlink)
        if parsed.scheme not in {"http", "https"}:
            raise NetdiskError("百度接口没有返回有效下载链接")
        destination = destination_for(source, plan, root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected_size = int(metadata.get("size", source.size) or 0)
        if destination.exists() and expected_size and destination.stat().st_size == expected_size:
            return DownloadResult(source.fs_id, source.path, str(destination), "skipped", size=expected_size)
        if destination.exists():
            destination = _unique_destination(destination)

        temp = destination.with_name(f".part-{uuid.uuid4().hex[:12]}")
        digest = hashlib.sha256()
        written = 0
        session = requests.Session()
        try:
            with session.get(
                dlink,
                params={"access_token": self.client.token},
                headers={"User-Agent": USER_AGENT},
                stream=True,
                allow_redirects=True,
                timeout=(15, 180),
            ) as response:
                if not response.ok:
                    raise NetdiskError(f"文件下载返回 HTTP {response.status_code}")
                if "application/json" in response.headers.get("Content-Type", "").casefold():
                    raise NetdiskError("下载接口返回了错误信息而不是文件")
                with temp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
                            digest.update(chunk)
                            written += len(chunk)
            if expected_size and written != expected_size:
                raise NetdiskError(f"文件大小校验失败：预期 {expected_size}，实际 {written}")
            os.replace(temp, destination)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        finally:
            session.close()
        return DownloadResult(
            source.fs_id,
            source.path,
            str(destination),
            "downloaded",
            size=written,
            sha256=digest.hexdigest(),
        )

    @staticmethod
    def write_manifest(root: Path, plan: SelectionPlan, results: list[DownloadResult]) -> Path:
        manifest = root / "PanFetch AI下载清单.json"
        payload = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "plan": plan.to_dict(),
            "summary": {
                "total": len(results),
                "downloaded": sum(item.status == "downloaded" for item in results),
                "skipped": sum(item.status == "skipped" for item in results),
                "failed": sum(item.status == "failed" for item in results),
                "cancelled": sum(item.status == "cancelled" for item in results),
            },
            "results": [item.to_dict() for item in results],
        }
        temp = manifest.with_name(f".{manifest.name}.{uuid.uuid4().hex[:8]}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, manifest)
        return manifest


def destination_for(item: RemoteItem, plan: SelectionPlan, root: Path) -> Path:
    remote = PurePosixPath(item.path)
    source = _matching_source(item.path, plan.source_paths)
    relative = PurePosixPath(item.path[len(source):].lstrip("/")) if source != "/" else remote.relative_to("/")
    name = safe_component(remote.name)
    if plan.organize_by == "type":
        relative_path = Path(_type_folder(remote.suffix.casefold())) / name
    elif plan.organize_by == "year":
        year_match = re.search(r"(?:19|20)\d{2}", item.path)
        relative_path = Path(year_match.group(0) if year_match else "未识别年份") / name
    elif plan.organize_by == "source":
        source_name = safe_component(PurePosixPath(source).name or "网盘根目录")
        relative_path = Path(source_name, *(safe_component(part) for part in relative.parts))
    else:
        relative_path = Path(*(safe_component(part) for part in relative.parts))
    destination = (root / relative_path).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError:
        raise ValueError("目标路径超出下载根目录") from None
    return destination


def safe_component(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).rstrip(" .") or "unnamed"
    if cleaned.split(".", 1)[0].upper() in WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def _matching_source(path: str, source_paths: list[str]) -> str:
    matches = [source.rstrip("/") or "/" for source in source_paths if path == source or path.startswith(f"{source.rstrip('/')}/")]
    return max(matches, key=len) if matches else "/"


def _type_folder(suffix: str) -> str:
    groups = {
        "文档": {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".md", ".txt", ".xmind"},
        "代码": {".java", ".py", ".js", ".ts", ".vue", ".html", ".css", ".sql", ".xml", ".json", ".yml", ".yaml"},
        "图片": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"},
        "音频": {".mp3", ".wav", ".ogg", ".m4a"},
        "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"},
    }
    for name, extensions in groups.items():
        if suffix in extensions:
            return name
    return "其他"


def _unique_destination(path: Path) -> Path:
    for index in range(1, 10000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError("无法为同名文件生成可用名称")


def _batched(values: list[int], size: int) -> list[list[int]]:
    return [values[index:index + size] for index in range(0, len(values), size)]
