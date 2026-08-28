from __future__ import annotations

from panfetch_ai.core.history import ConversationStore, repair_mojibake


def test_conversation_history_groups_and_loads_sessions(tmp_path) -> None:
    path = tmp_path / "history.jsonl"
    store = ConversationStore(path)
    first = store.new_session_id()
    second = store.new_session_id()
    store.append(first, "查找 Java 资料", "找到两个目录", "global", "/", "search", ["路由：search"])
    store.append(first, "下载其中 PDF", "下载计划已准备", "global", "/", "prepare_download", ["路由：prepare_download"])
    store.append(second, "查看 /课程", "已读取", "custom", "/课程", "list", [])

    turns = store.turns(first)
    assert [turn.request for turn in turns] == ["查找 Java 资料", "下载其中 PDF"]
    sessions = {item["session_id"]: item for item in store.sessions()}
    assert sessions[first]["title"] == "查找 Java 资料"
    assert sessions[first]["count"] == 2
    assert sessions[second]["count"] == 1


def test_conversation_history_ignores_malformed_lines(tmp_path) -> None:
    path = tmp_path / "history.jsonl"
    path.write_text('{"session_id":"ok","request":"问题"}\nnot-json\n[]\n', encoding="utf-8")
    turns = ConversationStore(path).turns()
    assert len(turns) == 1
    assert turns[0].session_id == "ok"


def test_conversation_history_deletes_only_selected_session_atomically(tmp_path) -> None:
    path = tmp_path / "history.jsonl"
    store = ConversationStore(path)
    first = store.new_session_id()
    second = store.new_session_id()
    store.append(first, "第一轮", "回答一", "global", "/", "help", [])
    store.append(first, "第二轮", "回答二", "global", "/", "help", [])
    store.append(second, "保留会话", "保留回答", "global", "/", "help", [])

    assert store.delete_session(first) == 2
    assert store.turns(first) == []
    assert [turn.request for turn in store.turns(second)] == ["保留会话"]
    assert store.delete_session(first) == 0


def test_history_repairs_existing_utf8_mojibake(tmp_path) -> None:
    path = tmp_path / "history.jsonl"
    path.write_text(
        '{"session_id":"s","request":"你好","response":"ä½ å¥½ï¼ææ¯ PanFetch AI","logs":["å·²å®æ"]}\n',
        encoding="utf-8",
    )
    store = ConversationStore(path)
    assert store.repair_encoding() == 2
    turn = store.turns("s")[0]
    assert turn.response == "你好，我是 PanFetch AI"
    assert turn.logs == ["已完成"]
    assert "ä½" not in path.read_text(encoding="utf-8")


def test_repair_mojibake_keeps_normal_text() -> None:
    assert repair_mojibake("正常中文 and English") == "正常中文 and English"
