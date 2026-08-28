from __future__ import annotations

import pytest

from panfetch_ai.core.operations import NetdiskOperationExecutor, build_operation_plan


def test_write_operations_require_complete_and_safe_paths() -> None:
    with pytest.raises(ValueError, match="同时指定"):
        build_operation_plan("move", {"source": "/a"})
    with pytest.raises(ValueError, match="不能移动或复制"):
        build_operation_plan("copy", {"source": "/a", "destination": "/a/child"})
    with pytest.raises(ValueError, match="整个网盘根目录"):
        build_operation_plan("share", {"paths": ["/"], "period": 7})


def test_share_period_and_password_are_normalized() -> None:
    share = build_operation_plan("share", {"paths": ["/普通目录/a.pdf"], "period": 29})
    assert share.arguments["period"] == 30
    assert share.arguments["paths"] == ["/普通目录/a.pdf"]
    assert share.backend == "mcp"
    transfer = build_operation_plan(
        "transfer",
        {
            "share_url": "https://pan.baidu.com/s/1abc",
            "extraction_code": "abcd",
            "destination": "/apps/bdpan/inbox",
        },
    )
    assert "abcd" not in transfer.summary
    assert "****" in transfer.summary


def test_native_operation_executor_dispatches_without_bdpan() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = []

        def create_directory(self, path):
            self.calls.append(("mkdir", path))

    client = Client()
    plan = build_operation_plan("mkdir", {"path": "/学习资料"})
    result = NetdiskOperationExecutor(client).execute(plan)
    assert client.calls == [("mkdir", "/学习资料")]
    assert result.action == "mkdir"


def test_share_executor_uses_official_mcp_client_instead_of_bdpan() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = []

        def create_share(self, paths, period):
            self.calls.append((paths, period))
            return {"link": "https://pan.baidu.com/s/example", "pwd": "a1b2"}

    class Bdpan:
        def run(self, *args):
            raise AssertionError("full-disk sharing must not use bdpan")

    client = Client()
    plan = build_operation_plan("share", {"paths": ["/普通目录/a.pdf"], "period": 7})
    result = NetdiskOperationExecutor(client, Bdpan()).execute(plan)

    assert client.calls == [(["/普通目录/a.pdf"], 7)]
    assert "提取码：a1b2" in result.message
