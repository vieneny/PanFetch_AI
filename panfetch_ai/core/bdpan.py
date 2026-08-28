from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse


BDPAN_ROOT = "/apps/bdpan"


class BdpanError(RuntimeError):
    pass


@dataclass(slots=True)
class BdpanStatus:
    available: bool
    mode: str
    detail: str


class BdpanBackend:
    """Adapter for features that the public OpenAPI/MCP implementation does not expose."""

    def __init__(self) -> None:
        self._session_id = f"{int(time.time())}-{secrets.token_hex(3)}"

    def status(self) -> BdpanStatus:
        executable = shutil.which("bdpan")
        if executable:
            return BdpanStatus(True, "native", f"bdpan：{executable}")
        if os.name == "nt" and shutil.which("wsl.exe"):
            try:
                probe = subprocess.run(
                    ["wsl.exe", "sh", "-lc", "command -v bdpan"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired):
                probe = None
            if probe is not None and probe.returncode == 0 and probe.stdout.strip():
                return BdpanStatus(True, "wsl", f"WSL bdpan：{probe.stdout.strip()}")
        return BdpanStatus(
            False,
            "unavailable",
            "未检测到 bdpan。仅分享链接转存和下载需要在 WSL 安装并登录 bdpan，不影响全盘分享。",
        )

    def local_path_argument(self, path: str) -> str:
        status = self.status()
        if status.mode != "wsl":
            return path
        match = re.fullmatch(r"([A-Za-z]):[\\/](.*)", path)
        if not match:
            return path
        drive, remainder = match.groups()
        return f"/mnt/{drive.casefold()}/{remainder.replace(chr(92), '/')}"

    def run(self, command: str, arguments: list[str], session_input: str) -> dict[str, Any]:
        status = self.status()
        if not status.available:
            raise BdpanError(status.detail)
        argv = ["bdpan", command, *arguments, "--json", "--agentname", "PanFetch-AI"]
        argv.extend(["--session-input", session_input, "--session-id", self._session_id])
        if status.mode == "wsl":
            argv = ["wsl.exe", *argv]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60 * 60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BdpanError(f"bdpan 执行失败：{exc}") from None
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise BdpanError(detail[-1200:] or f"bdpan 退出码 {completed.returncode}")
        output = completed.stdout.strip()
        if not output:
            return {"status": "success"}
        try:
            payload = json.loads(output)
        except ValueError:
            return {"status": "success", "message": output[-2000:]}
        if isinstance(payload, dict):
            return payload
        return {"status": "success", "items": payload}


def normalize_bdpan_path(path: str, allow_root: bool = True) -> str:
    value = str(path or "").strip().replace("我的应用数据", "/apps")
    if not value.startswith("/") or "\\" in value:
        raise ValueError("bdpan 网盘路径必须使用以 / 开头的绝对路径")
    normalized = str(PurePosixPath(value))
    if ".." in PurePosixPath(value).parts:
        raise ValueError("网盘路径不能包含 ..")
    if normalized != BDPAN_ROOT and not normalized.startswith(f"{BDPAN_ROOT}/"):
        raise ValueError("分享、转存相关操作只能访问我的应用数据/bdpan")
    if not allow_root and normalized == BDPAN_ROOT:
        raise ValueError("请指定我的应用数据/bdpan 下的文件或目录")
    return normalized


def bdpan_relative_path(path: str) -> str:
    normalized = normalize_bdpan_path(path)
    return normalized.removeprefix(f"{BDPAN_ROOT}/") if normalized != BDPAN_ROOT else ""


def validate_share_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.casefold() != "pan.baidu.com" or not parsed.path.startswith("/s/"):
        raise ValueError("分享链接必须是 https://pan.baidu.com/s/... 格式")
    return url
