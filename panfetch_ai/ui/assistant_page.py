from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatInput(QTextEdit):
    send_requested = Signal()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            event.accept()
            if not event.isAutoRepeat():
                self.send_requested.emit()
            return
        super().keyPressEvent(event)


class ConversationView(QTextEdit):
    """Role-aware transcript with a restrained highlight for user prompts."""

    USER_BACKGROUND = QColor("#152934")
    USER_LABEL = QColor("#6ADBE8")
    USER_TEXT = QColor("#C5F2F5")
    ASSISTANT_LABEL = QColor("#58D6A2")
    ASSISTANT_TEXT = QColor("#E9EFF4")
    STATUS_TEXT = QColor("#F0A09B")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setObjectName("homeConversation")
        self.setPlaceholderText("输入一个问题，例如：查找 Java 集合讲义，并告诉我它们在哪。")

    def append_message(self, role: str, text: str) -> None:
        normalized_role = "user" if role == "user" else "assistant"
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.toPlainText():
            cursor.insertBlock(self._separator_format())
            cursor.insertBlock(self._block_format(normalized_role, label=True))
        else:
            cursor.setBlockFormat(self._block_format(normalized_role, label=True))

        cursor.setCharFormat(self._char_format(normalized_role, label=True))
        cursor.insertText("我的提问" if normalized_role == "user" else "PanFetch AI")
        cursor.insertBlock(self._block_format(normalized_role, label=False))
        cursor.setCharFormat(self._char_format(normalized_role, label=False))
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def append_stream_text(self, text: str, *, status: bool = False) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        char_format = self._char_format("assistant", label=False)
        if status:
            char_format.setForeground(self.STATUS_TEXT)
        cursor.setCharFormat(char_format)
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    @classmethod
    def _char_format(cls, role: str, *, label: bool) -> QTextCharFormat:
        char_format = QTextCharFormat()
        if label:
            char_format.setForeground(cls.USER_LABEL if role == "user" else cls.ASSISTANT_LABEL)
            char_format.setFontWeight(QFont.Weight.DemiBold)
        else:
            char_format.setForeground(cls.USER_TEXT if role == "user" else cls.ASSISTANT_TEXT)
        return char_format

    @classmethod
    def _block_format(cls, role: str, *, label: bool) -> QTextBlockFormat:
        block_format = QTextBlockFormat()
        block_format.setLeftMargin(12 if role == "user" else 4)
        block_format.setRightMargin(12 if role == "user" else 4)
        block_format.setTopMargin(8 if label else 1)
        block_format.setBottomMargin(1 if label else 9)
        if role == "user":
            block_format.setBackground(cls.USER_BACKGROUND)
        return block_format

    @staticmethod
    def _separator_format() -> QTextBlockFormat:
        block_format = QTextBlockFormat()
        block_format.setTopMargin(3)
        block_format.setBottomMargin(3)
        return block_format


class AssistantPage(QWidget):
    """Focused two-column AI workspace with diagnostics hidden by default."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homePage")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        history_panel = QFrame()
        history_panel.setObjectName("historyRail")
        history_panel.setFixedWidth(218)
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(14, 16, 12, 14)
        history_layout.setSpacing(10)
        history_header = QHBoxLayout()
        history_title = QLabel("会话")
        history_title.setProperty("sectionTitle", True)
        self.new_chat_button = QPushButton("新建")
        self.new_chat_button.setToolTip("新建 AI 问答会话")
        history_header.addWidget(history_title)
        history_header.addStretch(1)
        history_header.addWidget(self.new_chat_button)
        history_layout.addLayout(history_header)
        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list, 1)
        root.addWidget(history_panel)

        chat_panel = QFrame()
        chat_panel.setObjectName("chatSurface")
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.setContentsMargins(22, 18, 22, 16)
        chat_layout.setSpacing(10)

        heading = QHBoxLayout()
        title = QLabel("AI 问答")
        title.setObjectName("homeTitle")
        heading.addWidget(title)
        heading.addStretch(1)
        self.open_result_button = QPushButton("查看结果")
        self.open_result_button.setText("查看计划")
        heading.addWidget(self.open_result_button)
        chat_layout.addLayout(heading)

        scope_bar = QFrame()
        scope_bar.setObjectName("scopeBar")
        scope_layout = QHBoxLayout(scope_bar)
        scope_layout.setContentsMargins(10, 7, 8, 7)
        scope_layout.setSpacing(8)
        scope_label = QLabel("范围")
        scope_label.setProperty("muted", True)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("全局网盘", "global")
        self.scope_combo.addItem("当前目录", "current")
        self.scope_combo.addItem("指定路径", "custom")
        self.scope_path = QLineEdit("/")
        self.scope_path.setFont(QFont("Cascadia Mono", 10))
        self.scope_path.setEnabled(False)
        self.use_current_button = QPushButton("取当前目录")
        scope_layout.addWidget(scope_label)
        scope_layout.addWidget(self.scope_combo)
        scope_layout.addWidget(self.scope_path, 1)
        scope_layout.addWidget(self.use_current_button)
        chat_layout.addWidget(scope_bar)

        self.conversation = ConversationView()
        chat_layout.addWidget(self.conversation, 1)

        status_row = QHBoxLayout()
        self.stage = QLabel("等待提问")
        self.stage.setObjectName("assistantSteps")
        self.stage.setWordWrap(False)
        self.details_toggle = QPushButton("运行详情")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self.details_toggle.toggled.connect(self._toggle_details)
        status_row.addWidget(self.stage, 1)
        status_row.addWidget(self.details_toggle)
        chat_layout.addLayout(status_row)

        self.details_panel = QFrame()
        self.details_panel.setObjectName("assistantDetails")
        details_layout = QHBoxLayout(self.details_panel)
        details_layout.setContentsMargins(10, 10, 10, 10)
        details_layout.setSpacing(10)
        thinking_column = QVBoxLayout()
        thinking_title = QLabel("思考摘要")
        thinking_title.setProperty("muted", True)
        self.thinking = QPlainTextEdit()
        self.thinking.setReadOnly(True)
        self.thinking.setObjectName("thinkingStream")
        self.thinking.setPlaceholderText("模型执行阶段会显示在这里")
        thinking_column.addWidget(thinking_title)
        thinking_column.addWidget(self.thinking, 1)
        trace_column = QVBoxLayout()
        trace_title = QLabel("工具日志")
        trace_title.setProperty("muted", True)
        self.trace = QPlainTextEdit()
        self.trace.setReadOnly(True)
        self.trace.setObjectName("traceStream")
        self.trace.setFont(QFont("Cascadia Mono", 9))
        self.trace.setPlaceholderText("路径、工具调用和扫描日志")
        trace_column.addWidget(trace_title)
        trace_column.addWidget(self.trace, 1)
        details_layout.addLayout(thinking_column, 1)
        details_layout.addLayout(trace_column, 1)
        self.details_panel.setMaximumHeight(210)
        self.details_panel.setVisible(False)
        chat_layout.addWidget(self.details_panel)

        self.input = ChatInput()
        self.input.setObjectName("assistantComposer")
        self.input.setPlaceholderText("输入问题；Enter 发送，Shift+Enter 换行")
        self.input.setMaximumHeight(92)
        chat_layout.addWidget(self.input)
        input_actions = QHBoxLayout()
        input_actions.addStretch(1)
        self.stop_button = QPushButton("中断")
        self.stop_button.setProperty("danger", True)
        self.stop_button.setToolTip("中断当前 AI 请求")
        self.stop_button.setEnabled(False)
        self.send_button = QPushButton("发送")
        self.send_button.setProperty("primary", True)
        input_actions.addWidget(self.stop_button)
        input_actions.addWidget(self.send_button)
        chat_layout.addLayout(input_actions)
        root.addWidget(chat_panel, 1)

    def _toggle_details(self, expanded: bool) -> None:
        self.details_panel.setVisible(expanded)
        arrow = QStyle.StandardPixmap.SP_ArrowDown if expanded else QStyle.StandardPixmap.SP_ArrowRight
        self.details_toggle.setIcon(self.style().standardIcon(arrow))
