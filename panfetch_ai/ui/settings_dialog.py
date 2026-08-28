from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode, urlparse

from PySide6.QtCore import QThreadPool, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from panfetch_ai.core.config import AppConfig, ConfigStore, LLMConfig, LLM_PRESETS, parse_headers
from panfetch_ai.core.planner import LLMPlanner
from panfetch_ai.ui.workers import TaskRunner


class SettingsDialog(QDialog):
    def __init__(self, store: ConfigStore, parent: QWidget | None = None, initial_tab: str = "") -> None:
        super().__init__(parent)
        self.store = store
        self.config = store.load()
        self.thread_pool = QThreadPool.globalInstance()
        self._test_runner: TaskRunner | None = None
        self.setWindowTitle("PanFetch AI 设置")
        self.setMinimumSize(650, 540)
        self._build_ui()
        self._load_values()
        if initial_tab == "baidu":
            self.tabs.setCurrentWidget(self.baidu_page)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.baidu_page = self._build_baidu_tab()
        self.tabs.addTab(self.baidu_page, "百度网盘")
        self.tabs.addTab(self._build_llm_tab(), "LLM")
        self.tabs.addTab(self._build_download_tab(), "下载")
        root.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_baidu_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.baidu_client_id = QLineEdit()
        self.baidu_client_id.setPlaceholderText("百度网盘开放平台应用 API Key")
        form.addRow("OAuth Client ID", self.baidu_client_id)
        authorize_row = QWidget()
        authorize_layout = QHBoxLayout(authorize_row)
        authorize_layout.setContentsMargins(0, 0, 0, 0)
        authorize = QPushButton("打开百度授权页")
        authorize.setProperty("primary", True)
        authorize.clicked.connect(self._open_baidu_authorization)
        authorize_layout.addWidget(authorize)
        authorize_layout.addStretch(1)
        form.addRow("重新授权", authorize_row)
        self.baidu_token = QLineEdit()
        self.baidu_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.baidu_token.setPlaceholderText("留空表示继续使用已加密保存的 Token")
        form.addRow("Access Token", self.baidu_token)
        self.baidu_auth_status = QLabel("1. 打开授权页并登录  2. 同意授权  3. 从成功页复制 Access Token 到上方。\nToken 使用 Windows DPAPI 加密，不写入配置文件或 Git。")
        self.baidu_auth_status.setProperty("muted", True)
        self.baidu_auth_status.setWordWrap(True)
        form.addRow("", self.baidu_auth_status)
        return page

    def _build_llm_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.provider = QComboBox()
        self.provider.addItems(LLM_PRESETS)
        self.provider.currentTextChanged.connect(self._apply_preset)
        self.api_mode = QComboBox()
        self.api_mode.addItem("Chat Completions", "chat_completions")
        self.api_mode.addItem("Responses", "responses")
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.example.com/v1")
        self.model = QLineEdit()
        self.model.setPlaceholderText("模型名称")
        self.llm_key = QLineEdit()
        self.llm_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_key.setPlaceholderText("留空表示不修改已保存 API Key")
        self.api_key_header = QComboBox()
        self.api_key_header.setEditable(True)
        self.api_key_header.addItems(["Authorization", "x-api-key", "api-key"])
        self.api_key_prefix = QComboBox()
        self.api_key_prefix.setEditable(True)
        self.api_key_prefix.addItems(["Bearer", ""])
        self.headers = QPlainTextEdit()
        self.headers.setPlaceholderText('{"X-Organization": "example"}')
        self.headers.setMaximumHeight(90)
        self.timeout = QSpinBox()
        self.timeout.setRange(10, 300)
        self.timeout.setSuffix(" 秒")
        form.addRow("服务预设", self.provider)
        form.addRow("接口方式", self.api_mode)
        form.addRow("Base URL", self.base_url)
        form.addRow("模型", self.model)
        form.addRow("API Key", self.llm_key)
        form.addRow("Key 请求头", self.api_key_header)
        form.addRow("Key 前缀", self.api_key_prefix)
        form.addRow("自定义请求头", self.headers)
        form.addRow("超时", self.timeout)
        test_row = QWidget()
        test_layout = QHBoxLayout(test_row)
        test_layout.setContentsMargins(0, 0, 0, 0)
        self.test_llm_button = QPushButton("检测连接")
        self.test_llm_button.setProperty("primary", True)
        self.test_llm_button.clicked.connect(self._test_llm_connection)
        self.llm_test_status = QLabel("使用当前输入值发起一次最小对话请求")
        self.llm_test_status.setProperty("muted", True)
        test_layout.addWidget(self.test_llm_button)
        test_layout.addWidget(self.llm_test_status, 1)
        form.addRow("连接检测", test_row)
        hint = QLabel("兼容 OpenAI、DeepSeek、硅基流动、Ollama 及其他 OpenAI-compatible 服务。")
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        form.addRow("", hint)
        return page

    def _build_download_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.download_root = QLineEdit()
        browse = QPushButton("选择目录")
        browse.clicked.connect(self._choose_directory)
        row_layout.addWidget(self.download_root, 1)
        row_layout.addWidget(browse)
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 10)
        self.concurrency.setToolTip("百度未公开 SVIP 固定并发上限，建议保持 5 到 10")
        form.addRow("下载根目录", row)
        form.addRow("并发数", self.concurrency)
        return page

    def _load_values(self) -> None:
        self.provider.setCurrentText(self.config.llm.provider if self.config.llm.provider in LLM_PRESETS else "自定义")
        self.baidu_client_id.setText(self.config.baidu_oauth_client_id)
        self.base_url.setText(self.config.llm.base_url)
        self.model.setText(self.config.llm.model)
        self.headers.setPlainText(json.dumps(self.config.llm.custom_headers, ensure_ascii=False, indent=2) if self.config.llm.custom_headers else "")
        self.timeout.setValue(self.config.llm.timeout_seconds)
        self.api_key_header.setCurrentText(self.config.llm.api_key_header)
        self.api_key_prefix.setCurrentText(self.config.llm.api_key_prefix)
        mode_index = self.api_mode.findData(self.config.llm.api_mode)
        self.api_mode.setCurrentIndex(max(mode_index, 0))
        self.download_root.setText(self.config.download_root)
        self.concurrency.setValue(self.config.concurrency)

    def _apply_preset(self, provider: str) -> None:
        preset = LLM_PRESETS.get(provider)
        if not preset or provider == "自定义":
            return
        self.base_url.setText(preset["base_url"])
        self.model.setText(preset["model"])
        index = self.api_mode.findData(preset["api_mode"])
        self.api_mode.setCurrentIndex(max(index, 0))

    def _choose_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择下载根目录", self.download_root.text())
        if selected:
            self.download_root.setText(selected)

    def _open_baidu_authorization(self) -> None:
        client_id = self.baidu_client_id.text().strip()
        if not client_id:
            QMessageBox.warning(self, "无法打开授权页", "请先填写百度网盘开放平台 OAuth Client ID。")
            return
        query = urlencode(
            {
                "response_type": "token",
                "client_id": client_id,
                "redirect_uri": "oob",
                "scope": "basic,netdisk",
            }
        )
        QDesktopServices.openUrl(QUrl(f"https://openapi.baidu.com/oauth/2.0/authorize?{query}"))
        self.baidu_auth_status.setText("授权页已打开。完成授权后，从成功页地址中复制 access_token 的值并粘贴到 Access Token。")

    def _form_llm_config(self) -> LLMConfig:
        base_url = self.base_url.text().strip()
        if base_url and urlparse(base_url).scheme not in {"http", "https"}:
            raise ValueError("LLM Base URL 必须以 http:// 或 https:// 开头")
        return LLMConfig(
            provider=self.provider.currentText(),
            base_url=base_url,
            api_mode=str(self.api_mode.currentData()),
            model=self.model.text().strip(),
            api_key_header=self.api_key_header.currentText().strip() or "Authorization",
            api_key_prefix=self.api_key_prefix.currentText().strip(),
            custom_headers=parse_headers(self.headers.toPlainText()),
            timeout_seconds=self.timeout.value(),
        )

    def _test_llm_connection(self) -> None:
        if self._test_runner is not None:
            return
        try:
            config = self._form_llm_config()
            api_key = self.llm_key.text().strip() or self.store.read_llm_key()
        except Exception as exc:
            QMessageBox.warning(self, "无法检测连接", str(exc))
            return

        def work(_: object) -> tuple[str, float]:
            started = time.perf_counter()
            reply = LLMPlanner(config, api_key).test_connection()
            return reply, time.perf_counter() - started

        def ready(result: tuple[str, float]) -> None:
            reply, elapsed = result
            self._test_runner = None
            self.test_llm_button.setEnabled(True)
            self.llm_test_status.setProperty("state", "success")
            self.llm_test_status.setText(f"连接正常 · {elapsed:.2f} 秒 · {config.model} · 回复：{reply[:40] or '成功'}")
            self.llm_test_status.style().unpolish(self.llm_test_status)
            self.llm_test_status.style().polish(self.llm_test_status)

        def failed(message: str) -> None:
            self._test_runner = None
            self.test_llm_button.setEnabled(True)
            self.llm_test_status.setProperty("state", "error")
            self.llm_test_status.setText(message)
            self.llm_test_status.style().unpolish(self.llm_test_status)
            self.llm_test_status.style().polish(self.llm_test_status)

        self.test_llm_button.setEnabled(False)
        self.llm_test_status.setText("正在发送最小对话请求…")
        runner = TaskRunner(work)
        self._test_runner = runner
        runner.signals.result.connect(ready)
        runner.signals.error.connect(failed)
        self.thread_pool.start(runner)

    def accept(self) -> None:
        try:
            root = Path(self.download_root.text().strip()).expanduser()
            if not root.is_absolute():
                raise ValueError("下载根目录必须是绝对路径")
            llm = self._form_llm_config()
            config = replace(
                self.config,
                download_root=str(root),
                concurrency=self.concurrency.value(),
                baidu_oauth_client_id=self.baidu_client_id.text().strip(),
                llm=llm,
            )
            self.store.save(config)
            if self.baidu_token.text().strip():
                self.store.write_baidu_token(self.baidu_token.text())
            if self.llm_key.text().strip():
                self.store.write_llm_key(self.llm_key.text())
            self.config = config
        except Exception as exc:
            QMessageBox.warning(self, "设置未保存", str(exc))
            return
        super().accept()
