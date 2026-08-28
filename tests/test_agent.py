from __future__ import annotations

from typing import Any

from panfetch_ai.core.agent import AgentDecision, NetdiskAgent, local_agent_decision, scan_source_items
from panfetch_ai.core.config import LLMConfig
from panfetch_ai.core.models import RemoteItem
from panfetch_ai.core.planner import LLMPlanner


class Response:
    ok = True
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


class Session:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def request(self, *args: Any, **kwargs: Any) -> Response:
        return Response(self.payload)


class Client:
    def list_directory(self, path: str, limit: int = 0) -> list[RemoteItem]:
        return [RemoteItem(1, f"{path.rstrip('/')}/文档.pdf", "文档.pdf", False, size=1024)]

    def walk(self, path: str, max_depth: int = -1, limit: int = 0, progress=None) -> list[RemoteItem]:
        if progress:
            progress(path, 2)
        return [
            RemoteItem(2, f"{path.rstrip('/')}/第一章", "第一章", True),
            RemoteItem(3, f"{path.rstrip('/')}/第一章/讲义.pdf", "讲义.pdf", False, size=2048),
        ]


def test_local_agent_routes_safe_read_actions() -> None:
    assert local_agent_decision("查看 /学习资料", "/").action == "list"
    search = local_agent_decision("搜索所有 PDF 文件", "/")
    assert search.action == "search"
    assert search.arguments["keyword"].casefold() == "pdf"
    assert local_agent_decision("显示 /学习资料 的目录结构", "/").action == "tree"
    assert local_agent_decision("下载 /学习资料 的讲义", "/").action == "prepare_download"


def test_disallowed_agent_action_becomes_help() -> None:
    decision = AgentDecision.from_dict({"action": "delete", "arguments": {"path": "/"}})
    assert decision.action == "help"


def test_llm_agent_decision_uses_controlled_json_action() -> None:
    session = Session(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"action":"search","arguments":{"path":"/资料","keyword":"PDF","limit":20},"reply":""}'
                    }
                }
            ]
        }
    )
    planner = LLMPlanner(LLMConfig(base_url="https://example.test/v1", model="model"), "key", session)
    decision = NetdiskAgent(planner, Client()).decide("找 PDF", "/", [], [], "F:\\downloads")
    assert decision.action == "search"
    assert decision.arguments["path"] == "/资料"


def test_agent_executes_list_with_local_fallback() -> None:
    planner = LLMPlanner(LLMConfig())
    result = NetdiskAgent(planner, Client()).run("查看 /学习资料", "/", [], [], "F:\\downloads")
    assert result.action == "list"
    assert result.path == "/学习资料"
    assert result.items[0].path == "/学习资料/文档.pdf"


def test_agent_inspects_material_inventory() -> None:
    result = NetdiskAgent(LLMPlanner(LLMConfig()), Client()).run("识别资料内容 /学习资料", "/", [], [], "F:\\downloads")
    assert result.action == "inspect"
    assert "目录：1 个" in result.message
    assert "pdf 1" in result.message


def test_execute_uses_conversation_context_for_download_plan() -> None:
    class RecordingPlanner(LLMPlanner):
        def __init__(self) -> None:
            super().__init__(LLMConfig())
            self.request = ""

        def create_plan(self, request, context_paths, default_destination, current_path="/"):
            self.request = request
            return super().create_plan(request, context_paths, default_destination, current_path)

    planner = RecordingPlanner()
    agent = NetdiskAgent(planner, Client())
    decision = AgentDecision("prepare_download")
    agent.execute(
        decision,
        "下载其中 PDF",
        "/课程",
        ["/课程/第一章/讲义.pdf"],
        "F:\\study",
        history=[("assistant", "已找到 /课程/第一章/讲义.pdf")],
    )
    assert "已找到 /课程/第一章/讲义.pdf" in planner.request


def test_direct_file_source_is_not_walked_as_directory() -> None:
    class FileClient:
        def __init__(self) -> None:
            self.walked = False

        def list_directory(self, path: str, limit: int = 0):
            assert path == "/课程"
            return [RemoteItem(9, "/课程/讲义.pdf", "讲义.pdf", False, size=500)]

        def walk(self, *args, **kwargs):
            self.walked = True
            return []

    client = FileClient()
    items = scan_source_items(client, "/课程/讲义.pdf", -1, 0)
    assert [item.fs_id for item in items] == [9]
    assert client.walked is False


def test_llm_write_action_only_builds_confirmation_plan(tmp_path) -> None:
    local_file = tmp_path / "data.csv"
    local_file.write_text("id,name\n1,test\n", encoding="utf-8")
    agent = NetdiskAgent(LLMPlanner(LLMConfig()), Client())
    result = agent.execute(
        AgentDecision("prepare_upload", {"local_path": str(local_file), "remote_path": "/资料"}),
        "上传 data.csv 到网盘资料目录",
        "/",
        [],
        str(tmp_path),
    )

    assert result.operation is not None
    assert result.operation.action == "upload"
    assert result.operation.arguments["remote_path"] == "/资料/data.csv"
    assert "确认后" in result.message


def test_local_agent_routes_share_transfer_to_confirmation_plan() -> None:
    decision = local_agent_decision("转存 https://pan.baidu.com/s/1abc 提取码 abcd", "/")
    assert decision.action == "prepare_transfer"
    assert decision.arguments["extraction_code"] == "abcd"
