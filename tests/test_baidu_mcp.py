from __future__ import annotations

from types import SimpleNamespace

import pytest

from panfetch_ai.core.baidu_mcp import BaiduMcpError, _safe_error, _tool_payload


def test_mcp_tool_payload_accepts_structured_result() -> None:
    result = SimpleNamespace(
        content=[],
        isError=False,
        structuredContent={"data": {"link": "https://pan.baidu.com/s/example", "pwd": "a1b2"}},
    )

    assert _tool_payload(result)["pwd"] == "a1b2"


def test_mcp_tool_payload_raises_tool_error() -> None:
    result = SimpleNamespace(
        content=[SimpleNamespace(text="授权已失效")],
        isError=True,
        structuredContent=None,
    )

    with pytest.raises(BaiduMcpError, match="授权已失效"):
        _tool_payload(result)


def test_mcp_error_redacts_complete_access_token() -> None:
    message = _safe_error(RuntimeError("request failed: ?access_token=secret-token&x=1"))

    assert "secret-token" not in message
    assert "access_token=***&x=1" in message
