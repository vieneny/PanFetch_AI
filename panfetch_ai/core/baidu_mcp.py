from __future__ import annotations

import asyncio
import json
import re
import secrets
import string
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client


MCP_SSE_BASE = "https://mcp-pan.baidu.com/sse"
SHARE_TOOL = "file_sharelink_set"


class BaiduMcpError(RuntimeError):
    pass


class BaiduMcpClient:
    """Small synchronous adapter around Baidu's official hosted MCP server."""

    def __init__(self, token: str) -> None:
        self.token = token

    def share_available(self) -> bool:
        return asyncio.run(self._share_available())

    def create_share(self, fs_ids: list[int], period: int) -> dict[str, Any]:
        if not fs_ids:
            raise ValueError("请至少选择一个需要分享的文件或文件夹")
        password = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
        return asyncio.run(self._create_share(fs_ids, period, password))

    async def _share_available(self) -> bool:
        async with self._session() as session:
            tools = await session.list_tools()
            return any(tool.name == SHARE_TOOL for tool in tools.tools)

    async def _create_share(self, fs_ids: list[int], period: int, password: str) -> dict[str, Any]:
        async with self._session() as session:
            result = await session.call_tool(
                SHARE_TOOL,
                {
                    "fsid_list": json.dumps([str(value) for value in fs_ids], separators=(",", ":")),
                    "period": period,
                    "pwd": password,
                    "remark": "PanFetch AI",
                },
                read_timeout_seconds=timedelta(seconds=90),
            )
        payload = _tool_payload(result)
        errno = payload.get("errno", payload.get("error_code", 0))
        if errno not in (0, "0", None):
            message = payload.get("errmsg") or payload.get("error_msg") or "未知错误"
            raise BaiduMcpError(f"百度网盘分享失败 {errno}: {message}")
        if not (payload.get("link") or payload.get("short_url")):
            raise BaiduMcpError(str(payload.get("message") or "百度网盘分享接口未返回分享链接"))
        payload.setdefault("pwd", password)
        return payload

    def _session(self):
        if not self.token:
            raise BaiduMcpError("尚未授权百度网盘")
        return _McpSession(self.token)


class _McpSession:
    def __init__(self, token: str) -> None:
        self.url = f"{MCP_SSE_BASE}?access_token={token}"
        self._sse_context: Any = None
        self._session_context: Any = None

    async def __aenter__(self) -> ClientSession:
        try:
            self._sse_context = sse_client(self.url, timeout=10, sse_read_timeout=120)
            streams = await self._sse_context.__aenter__()
            self._session_context = ClientSession(*streams)
            session = await self._session_context.__aenter__()
            await session.initialize()
            return session
        except Exception as exc:
            await self.__aexit__(type(exc), exc, exc.__traceback__)
            raise BaiduMcpError(f"无法连接百度网盘官方 MCP 服务：{_safe_error(exc)}") from None

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._session_context is not None:
            await self._session_context.__aexit__(exc_type, exc, traceback)
        if self._sse_context is not None:
            await self._sse_context.__aexit__(exc_type, exc, traceback)


def _tool_payload(result: Any) -> dict[str, Any]:
    texts = [str(block.text) for block in result.content if hasattr(block, "text")]
    if getattr(result, "isError", False):
        raise BaiduMcpError("；".join(texts) or "百度网盘 MCP 工具执行失败")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return _unwrap_payload(structured)
    for text in texts:
        try:
            decoded = json.loads(text)
        except ValueError:
            continue
        if isinstance(decoded, dict):
            return _unwrap_payload(decoded)
    return {"message": "；".join(texts)}


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "result"):
        nested = payload.get(key)
        if isinstance(nested, dict) and (nested.get("link") or nested.get("short_url") or nested.get("errno") is not None):
            return nested
    return payload


def _safe_error(exc: BaseException) -> str:
    message = re.sub(r"(access_token=)[^&\s'\"]+", r"\1***", str(exc), flags=re.IGNORECASE)
    return message[-500:] or type(exc).__name__
