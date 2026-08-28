from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QToolBar

from panfetch_ai.core.models import OperationPlan, OperationResult, PlanPreview, RemoteItem, SelectionPlan
from panfetch_ai.ui.assistant_page import AssistantPage, ConversationView
from panfetch_ai.ui.main_window import ChatInput, MainWindow
from panfetch_ai.ui.settings_dialog import SettingsDialog


def test_main_window_constructs(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("panfetch_ai.ui.main_window.QTimer.singleShot", lambda *_: None)
    monkeypatch.setattr("panfetch_ai.core.catalog.DEFAULT_DB", tmp_path / "catalog.db")
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "PanFetch AI"
    assert window.file_table.columnCount() == 7
    assert window.prompt_edit.placeholderText()
    assert window.page_stack.count() == 4
    assert window.operation_confirm.isEnabled() is False
    assert window.home_stop_button.isEnabled() is False
    assert "Enter 发送" in window.home_input.placeholderText()
    assert window.page_stack.currentWidget() is window.home_page
    assert window.page_stack.widget(2) is window.plan_page
    assert window.home_nav.property("active") is True
    assert window.home_nav.text() == "AI 问答"
    assert window.home_page.findChild(QLabel, "homeTitle").text() == "AI 问答"
    assert isinstance(window.home_page, AssistantPage)
    assert window.home_details_panel.isHidden() is True
    assert window.workspace_nav.property("active") is False
    assert window.scope_combo.currentData() == "global"
    assert window.scope_path.text() == "/"
    assert window.history_list is not None
    assert window.plan_table.columnCount() == 5
    assert window.workspace_plan_button.isEnabled() is False
    assert window.plan_download_button.isEnabled() is False
    toolbar = window.findChild(QToolBar)
    assert toolbar is not None
    assert "下载目录" not in [action.text() for action in toolbar.actions()]
    assert window.reauthorize_button.text() == "重新授权"
    assert window.logout_button.text() == "退出登录"
    monkeypatch.setattr(window, "load_directory", lambda *_: None)
    window._connection_ready(
        (
            {"netdisk_name": "示例账号", "uk": 42, "vip_type": 2},
            {"total": 1000, "used": 250, "free": 100, "expire": False},
            b"",
        )
    )
    assert window.account_name.text() == "示例账号"
    assert window.account_meta.text() == "SVIP · UID 42"
    assert window.quota_progress.value() == 250


def test_assistant_run_details_expand_only_on_request(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("panfetch_ai.ui.main_window.QTimer.singleShot", lambda *_: None)
    monkeypatch.setattr("panfetch_ai.core.catalog.DEFAULT_DB", tmp_path / "catalog.db")
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.home_details_toggle.isChecked() is False
    assert window.home_details_panel.isHidden() is True

    window.home_details_toggle.click()
    assert window.home_details_toggle.isChecked() is True
    assert window.home_details_panel.isHidden() is False

    window.home_details_toggle.click()
    assert window.home_details_toggle.isChecked() is False
    assert window.home_details_panel.isHidden() is True


def test_conversation_view_distinguishes_user_and_assistant(qtbot) -> None:
    view = ConversationView()
    qtbot.addWidget(view)
    view.append_message("user", "帮我查找集合讲义")
    view.append_message("assistant", "已找到相关资料。")

    assert view.toPlainText() == "我的提问\n帮我查找集合讲义\n\nPanFetch AI\n已找到相关资料。"
    user_cursor = view.document().find("我的提问")
    assistant_cursor = view.document().find("PanFetch AI")
    assert user_cursor.charFormat().foreground().color().name() == "#6adbe8"
    assert user_cursor.blockFormat().background().color().name() == "#152934"
    assert assistant_cursor.charFormat().foreground().color().name() == "#58d6a2"
    assert assistant_cursor.blockFormat().background().style() == Qt.BrushStyle.NoBrush


def test_chat_input_enter_sends_and_shift_enter_adds_line(qtbot) -> None:
    editor = ChatInput()
    qtbot.addWidget(editor)
    sent: list[bool] = []
    editor.send_requested.connect(lambda: sent.append(True))

    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert sent == [True]
    assert editor.toPlainText() == ""

    qtbot.keyClick(editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert sent == [True]
    assert editor.toPlainText() == "\n"


def test_interrupt_restores_chat_controls_immediately(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("panfetch_ai.ui.main_window.QTimer.singleShot", lambda *_: None)
    monkeypatch.setattr("panfetch_ai.core.catalog.DEFAULT_DB", tmp_path / "catalog.db")
    window = MainWindow()
    qtbot.addWidget(window)

    class Planner:
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    planner = Planner()
    saved: list[tuple] = []
    monkeypatch.setattr("panfetch_ai.ui.main_window.LLMPlanner.from_store", lambda *_: planner)
    monkeypatch.setattr(window, "_run_task", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(window.conversation_store, "append", lambda *args: saved.append(args))
    monkeypatch.setattr(window, "_reload_conversation_list", lambda: None)

    window.home_input.setPlainText("帮我查资料")
    window.send_home_request()
    assert window.agent_busy is True
    assert window.home_send_button.isEnabled() is False
    assert window.home_stop_button.isEnabled() is True

    window.interrupt_home_request()
    assert planner.cancelled is True
    assert window.agent_busy is False
    assert window.home_send_button.isEnabled() is True
    assert window.home_stop_button.isEnabled() is False
    assert window.home_stage.text() == "已中断"
    assert saved and saved[0][5] == "cancelled"


def test_plan_opens_on_dedicated_page(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("panfetch_ai.ui.main_window.QTimer.singleShot", lambda *_: None)
    monkeypatch.setattr("panfetch_ai.core.catalog.DEFAULT_DB", tmp_path / "catalog.db")
    window = MainWindow()
    qtbot.addWidget(window)
    item = RemoteItem(7, "/课程/讲义.pdf", "讲义.pdf", False, size=1024)
    plan = SelectionPlan(
        source_paths=["/课程"],
        include_extensions=[".pdf"],
        exclude_extensions=[".mp4"],
        destination=str(tmp_path),
        reasoning="只选择讲义",
    )
    window._plan_ready(PlanPreview(plan, [item], 2, {"命中排除扩展名": 2}))
    assert window.plan_table.rowCount() == 1
    assert window.plan_download_button.isEnabled() is True
    assert window.workspace_plan_button.isEnabled() is True
    assert window.open_result_button.text() == "查看下载计划"
    window.open_latest_result()
    assert window.page_stack.currentWidget() is window.plan_page
    assert "/课程" in window.plan_summary.text()


def test_share_plan_displays_official_mcp_backend(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("panfetch_ai.ui.main_window.QTimer.singleShot", lambda *_: None)
    monkeypatch.setattr("panfetch_ai.core.catalog.DEFAULT_DB", tmp_path / "catalog.db")
    window = MainWindow()
    qtbot.addWidget(window)

    window._show_operation_plan(
        OperationPlan(
            "share",
            "生成百度网盘分享链接",
            "分享内容：/课程/讲义.pdf",
            {"paths": ["/课程/讲义.pdf"], "period": 7},
            backend="mcp",
        )
    )

    backend_text = window.operation_backend.text()
    assert "百度官方 MCP（全盘分享）" in backend_text
    assert "不依赖 bdpan" in backend_text
    assert "bdpan Skill 后端" not in backend_text
    assert window.operation_confirm.isEnabled() is True
    assert window.copy_share_button.isHidden() is False
    assert window.copy_share_button.isEnabled() is False

    window._operation_ready(
        OperationResult(
            "share",
            "分享链接已生成：https://pan.baidu.com/s/example\n提取码：a1b2",
            {"link": "https://pan.baidu.com/s/example", "pwd": "a1b2"},
        )
    )
    assert window.copy_share_button.isEnabled() is True

    window.copy_share_result()
    assert QApplication.clipboard().text() == (
        "分享链接：https://pan.baidu.com/s/example\n提取码：a1b2\n有效期：7 天"
    )


def test_connection_status_dialog_contains_baidu_and_llm(qtbot, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("panfetch_ai.ui.main_window.QTimer.singleShot", lambda *_: None)
    monkeypatch.setattr("panfetch_ai.core.catalog.DEFAULT_DB", tmp_path / "catalog.db")
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "load_directory", lambda *_: None)
    captured: list[str] = []
    monkeypatch.setattr("panfetch_ai.ui.main_window.QMessageBox.exec", lambda box: captured.append(box.text()))
    window._connection_status_ready(
        {
            "baidu_ok": True,
            "baidu_detail": "已连接：示例账号",
            "account": {"netdisk_name": "示例账号", "vip_type": 2},
            "quota": {},
            "avatar": b"",
            "llm_ok": True,
            "llm_detail": "已连接：example-model · 响应正常",
            "share_ok": True,
            "share_detail": "百度官方 MCP 全盘分享服务可用",
            "bdpan_ok": False,
            "bdpan_detail": "未检测到 bdpan。仅分享链接转存和下载需要在 WSL 安装并登录 bdpan，不影响全盘分享。",
        }
    )
    assert captured
    assert "百度网盘：正常" in captured[0]
    assert "LLM：正常" in captured[0]
    assert "全盘分享：可用" in captured[0]
    assert "分享链接转存/下载：未配置（可选）" in captured[0]
    assert "不影响全盘分享" in captured[0]


def test_settings_uses_unsaved_llm_values(qtbot, tmp_path) -> None:
    from panfetch_ai.core.config import ConfigStore

    store = ConfigStore(tmp_path / "settings.json", tmp_path / "secrets")
    dialog = SettingsDialog(store)
    qtbot.addWidget(dialog)
    dialog.provider.setCurrentText("自定义")
    dialog.base_url.setText("https://gateway.example/v1")
    dialog.model.setText("example-model")
    dialog.api_mode.setCurrentIndex(dialog.api_mode.findData("chat_completions"))
    config = dialog._form_llm_config()
    assert config.base_url == "https://gateway.example/v1"
    assert config.model == "example-model"
    assert config.api_mode == "chat_completions"
    assert dialog.test_llm_button.text() == "检测连接"
