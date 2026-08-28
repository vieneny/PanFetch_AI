from __future__ import annotations

from typing import Any

from panfetch_ai.core.agent import AgentDecision, AgentResult
from panfetch_ai.core.assistant_workflow import AssistantWorkflow
from panfetch_ai.core.models import RemoteItem


class Planner:
    configured = False


class Agent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def decide(self, request, scope_path, visible_paths, history, destination):
        self.calls.append(("route", (request, scope_path, visible_paths, history, destination)))
        return AgentDecision("list", {"path": scope_path})

    def execute(self, decision, request, scope_path, visible_paths, destination, progress, history):
        self.calls.append(("tool", (decision.action, scope_path, history)))
        progress({"path": scope_path, "count": 1})
        item = RemoteItem(1, f"{scope_path.rstrip('/')}/讲义.pdf", "讲义.pdf", False, size=10)
        return AgentResult("list", "已找到讲义", [item], scope_path)


def test_graph_routes_then_executes_with_scope_and_history(monkeypatch) -> None:
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    agent = Agent()
    events: list[tuple[str, str]] = []
    history = [("user", "先找课程资料"), ("assistant", "已找到 /课程")]
    result = AssistantWorkflow(Planner(), agent).run(
        "查看里面的讲义",
        "/课程",
        ["/课程/第一章"],
        history,
        "F:\\study",
        lambda kind, text: events.append((kind, text)),
    )

    assert [name for name, _ in agent.calls] == ["route", "tool"]
    assert agent.calls[0][1][1] == "/课程"
    assert agent.calls[1][1][2] == history
    assert result.action == "list"
    assert result.answer == "已找到讲义"
    assert any(kind == "log" and "扫描 /课程" in text for kind, text in events)
