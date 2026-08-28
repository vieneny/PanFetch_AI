from __future__ import annotations

from typing import Any

import pytest

from panfetch_ai.core.cancellation import CancellationToken, OperationCancelled
from panfetch_ai.core.config import LLMConfig
from panfetch_ai.core.planner import LLMPlanner, local_plan


class Response:
    ok = True
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


class Session:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.request_args: dict[str, Any] = {}

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        self.request_args = {"method": method, "url": url, **kwargs}
        return Response(self.response)


class StreamResponse(Response):
    def __init__(self, lines: list[str]) -> None:
        super().__init__({})
        self.lines = lines

    def iter_lines(self, decode_unicode: bool = False):
        return iter(self.lines)


class StreamSession:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def request(self, *args: Any, **kwargs: Any) -> StreamResponse:
        return StreamResponse(self.lines)


def test_chat_completions_plan_uses_generic_bearer_key() -> None:
    session = Session(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"source_paths":["/学习资料"],"include_extensions":[".pdf"],"destination":"F:\\\\study","organize_by":"source"}'
                    }
                }
            ]
        }
    )
    planner = LLMPlanner(
        LLMConfig(base_url="https://example.test/v1", model="model", api_mode="chat_completions"),
        "api-secret",
        session,
    )
    plan = planner.create_plan("下载 PDF", ["/学习资料"], "F:\\default")
    assert plan.source_paths == ["/学习资料"]
    assert plan.include_extensions == [".pdf"]
    assert session.request_args["headers"]["Authorization"] == "Bearer api-secret"
    assert session.request_args["url"].endswith("/chat/completions")


def test_connection_probe_uses_chat_completions_without_json_mode() -> None:
    session = Session({"choices": [{"message": {"content": "连接正常"}}]})
    planner = LLMPlanner(
        LLMConfig(base_url="https://example.test/v1", model="model", api_mode="chat_completions"),
        "api-secret",
        session,
    )
    assert planner.test_connection() == "连接正常"
    assert session.request_args["url"].endswith("/chat/completions")
    assert "response_format" not in session.request_args["json"]


def test_responses_plan_parses_output_text() -> None:
    session = Session(
        {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"source_paths":["/项目文档"],"exclude_extensions":[".mp4"],"destination":"F:\\\\AI"}',
                        }
                    ]
                }
            ]
        }
    )
    planner = LLMPlanner(LLMConfig(base_url="https://example.test/v1", model="m", api_mode="responses"), session=session)
    plan = planner.create_plan("不要视频", ["/项目文档"], "F:\\AI")
    assert plan.exclude_extensions == [".mp4"]
    assert session.request_args["url"].endswith("/responses")


def test_custom_api_key_header_keeps_secret_out_of_custom_headers() -> None:
    session = Session({"data": []})
    config = LLMConfig(
        base_url="https://example.test/v1",
        model="m",
        api_key_header="x-api-key",
        api_key_prefix="",
    )
    planner = LLMPlanner(config, "secret", session)
    planner.list_models()
    assert session.request_args["headers"]["x-api-key"] == "secret"


def test_local_plan_understands_paths_and_safe_exclusions() -> None:
    plan = local_plan("查看 /学习资料，不要视频，下载到 F:\\study，按来源目录整理", "/", "F:\\default")
    assert plan.source_paths == ["/学习资料"]
    assert plan.destination.startswith("F:\\study")
    assert ".mp4" in plan.exclude_extensions
    assert plan.organize_by == "source"


def test_chat_stream_separates_reasoning_and_answer() -> None:
    session = StreamSession(
        [
            'data: {"choices":[{"delta":{"reasoning_content":"先检索"}}]}',
            'data: {"choices":[{"delta":{"content":"找到"}}]}',
            'data: {"choices":[{"delta":{"content":"资料"}}]}',
            "data: [DONE]",
        ]
    )
    planner = LLMPlanner(LLMConfig(base_url="https://example.test/v1", model="m"), "key", session)
    events: list[tuple[str, str]] = []
    answer = planner.stream_chat([{"role": "user", "content": "查资料"}], lambda kind, text: events.append((kind, text)))
    assert answer == "找到资料"
    assert events == [("thinking", "先检索"), ("answer", "找到"), ("answer", "资料")]


def test_chat_stream_decodes_utf8_bytes_without_response_charset() -> None:
    session = StreamSession(
        [
            'data: {"choices":[{"delta":{"content":"你好，我是网盘助手"}}]}'.encode("utf-8"),
            b"data: [DONE]",
        ]
    )
    planner = LLMPlanner(LLMConfig(base_url="https://example.test/v1", model="m"), "key", session)
    assert planner.stream_chat([{"role": "user", "content": "你好"}]) == "你好，我是网盘助手"


def test_chat_stream_stops_when_cancelled() -> None:
    token = CancellationToken()
    session = StreamSession(
        [
            'data: {"choices":[{"delta":{"content":"第一段"}}]}',
            'data: {"choices":[{"delta":{"content":"不应继续"}}]}',
        ]
    )
    planner = LLMPlanner(
        LLMConfig(base_url="https://example.test/v1", model="m"),
        "key",
        session,
        token,
    )

    with pytest.raises(OperationCancelled, match="用户中断"):
        planner.stream_chat(
            [{"role": "user", "content": "查资料"}],
            lambda _kind, _text: planner.cancel(),
        )
