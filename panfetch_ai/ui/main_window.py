from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from panfetch_ai.core.catalog import Catalog
from panfetch_ai.core.agent import NetdiskAgent, matches_category
from panfetch_ai.core.assistant_workflow import AssistantRunResult, AssistantWorkflow
from panfetch_ai.core.bdpan import BdpanBackend
from panfetch_ai.core.cancellation import CancellationToken
from panfetch_ai.core.config import ConfigStore
from panfetch_ai.core.downloader import DownloadControl, DownloadManager
from panfetch_ai.core.models import OperationPlan, OperationResult, PlanPreview, RemoteItem, SelectionPlan
from panfetch_ai.core.history import ConversationStore
from panfetch_ai.core.netdisk import BaiduNetdiskClient, NetdiskError, normalize_remote_path
from panfetch_ai.core.operations import NetdiskOperationExecutor, build_operation_plan
from panfetch_ai.core.plan_history import PlanHistoryRecord, PlanHistoryStore, PlanHistorySummary
from panfetch_ai.core.plan_preview import download_preview_tree
from panfetch_ai.core.planner import LLMPlanner
from panfetch_ai.core.rules import build_preview
from panfetch_ai.core.structure import chapter_lines, items_to_csv, tree_text
from panfetch_ai.ui.assistant_page import AssistantPage, ChatInput
from panfetch_ai.ui.download_plan_tree import DownloadPlanTree
from panfetch_ai.ui.plan_history_page import PlanHistoryPage
from panfetch_ai.ui.settings_dialog import SettingsDialog
from panfetch_ai.ui.workers import TaskRunner
from panfetch_ai.logging_setup import log_info


def format_share_copy_text(result: OperationResult, plan: OperationPlan) -> str:
    details = result.details
    link = str(details.get("link") or details.get("short_url") or details.get("url") or "").strip()
    if not link:
        return ""
    password = str(details.get("pwd") or details.get("password") or "").strip()
    period = int(plan.arguments.get("period") or 0)
    period_label = "永久" if period == 0 else f"{period} 天"
    lines = [f"分享链接：{link}"]
    if password:
        lines.append(f"提取码：{password}")
    lines.append(f"有效期：{period_label}")
    return "\n".join(lines)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = ConfigStore()
        self.config = self.store.load()
        self.catalog = Catalog()
        self.conversation_store = ConversationStore()
        self.conversation_store.repair_encoding()
        plan_history_path = os.getenv("PANFETCH_PLAN_HISTORY_DB", "").strip()
        self.plan_history_store = PlanHistoryStore(Path(plan_history_path) if plan_history_path else None)
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[TaskRunner] = set()
        self.current_path = "/"
        self.current_items: list[RemoteItem] = []
        self.current_plan: SelectionPlan | None = None
        self.current_preview: PlanPreview | None = None
        self.current_operation: OperationPlan | None = None
        self._share_copy_text = ""
        self.download_control: DownloadControl | None = None
        self.download_running = False
        self.download_paused = False
        self.agent_busy = False
        self.agent_history_entries: list[tuple[str, str]] = []
        self.session_id = self.conversation_store.new_session_id()
        self._home_answer_started = False
        self._home_logs: list[str] = []
        self._home_run_id = 0
        self._home_cancellation: CancellationToken | None = None
        self._home_planner: LLMPlanner | None = None

        self.setWindowTitle("PanFetch AI")
        self.setMinimumSize(1120, 720)
        self.resize(1480, 900)
        self._build_ui()
        if not os.getenv("PANFETCH_SKIP_AUTOCONNECT"):
            QTimer.singleShot(100, self.check_connection)

    def _build_ui(self) -> None:
        self._build_toolbar()
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.page_stack = QStackedWidget()
        self.home_page = self._build_home_page()
        self.workspace_page = self._build_workspace_page()
        self.plan_page = self._build_plan_page()
        self.operation_page = self._build_operation_page()
        self.plan_history_page = self._build_plan_history_page()
        self.page_stack.addWidget(self.home_page)
        self.page_stack.addWidget(self.workspace_page)
        self.page_stack.addWidget(self.plan_page)
        self.page_stack.addWidget(self.operation_page)
        self.page_stack.addWidget(self.plan_history_page)
        central_layout.addWidget(self.page_stack, 1)
        central_layout.addWidget(self._build_task_bar())
        self.setCentralWidget(central)
        self.switch_page(0)
        self._reload_conversation_list()
        self._reload_plan_history()
        self.statusBar().showMessage("正在检查百度网盘授权…")

    def _build_workspace_page(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_directory_panel())
        splitter.addWidget(self._build_file_panel())
        splitter.addWidget(self._build_action_panel())
        splitter.setSizes([280, 760, 390])
        splitter.setStretchFactor(1, 1)
        return splitter

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        brand = QLabel("PanFetch AI")
        brand.setObjectName("brandLabel")
        brand_font = QFont("Microsoft YaHei UI", 14, QFont.Weight.DemiBold)
        brand.setFont(brand_font)
        brand.setMinimumWidth(140)
        toolbar.addWidget(brand)
        toolbar.addSeparator()

        self.home_nav = QPushButton("AI 问答")
        self.home_nav.setProperty("nav", True)
        self.home_nav.clicked.connect(lambda: self.switch_page(0))
        toolbar.addWidget(self.home_nav)
        self.workspace_nav = QPushButton("网盘工作台")
        self.workspace_nav.setProperty("nav", True)
        self.workspace_nav.clicked.connect(lambda: self.switch_page(1))
        toolbar.addWidget(self.workspace_nav)
        toolbar.addSeparator()

        self.refresh_action = QAction(self._icon(QStyle.StandardPixmap.SP_BrowserReload), "刷新", self)
        self.refresh_action.setToolTip("刷新当前网盘目录")
        self.refresh_action.triggered.connect(lambda: self.load_directory(self.current_path))
        toolbar.addAction(self.refresh_action)

        account_action = QAction(self._icon(QStyle.StandardPixmap.SP_DriveNetIcon), "检查连接", self)
        account_action.triggered.connect(self.show_connection_status)
        toolbar.addAction(account_action)

        settings_action = QAction(self._icon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "设置", self)
        settings_action.triggered.connect(lambda: self.open_settings())
        toolbar.addAction(settings_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.connection_label = QLabel("未检查")
        self.connection_label.setProperty("status", "error")
        toolbar.addWidget(self.connection_label)

    def switch_page(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        is_home = index in {0, 4}
        is_workspace = index in {1, 2, 3}
        self.home_nav.setProperty("active", is_home)
        self.workspace_nav.setProperty("active", is_workspace)
        for button in (self.home_nav, self.workspace_nav):
            button.style().unpolish(button)
            button.style().polish(button)
        self.refresh_action.setVisible(index == 1)
        if hasattr(self, "task_bar"):
            self.task_bar.setVisible(index == 1 or (index == 2 and self.download_running))

    def _build_home_page(self) -> QWidget:
        page = AssistantPage()
        page.new_chat_button.clicked.connect(self.new_conversation)
        page.history_list.itemClicked.connect(self.load_conversation)
        page.open_result_button.clicked.connect(self.open_plan_history)
        page.scope_combo.currentIndexChanged.connect(self._scope_changed)
        page.use_current_button.clicked.connect(self._use_current_scope)
        page.input.send_requested.connect(self.send_home_request)
        page.send_button.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowForward))
        page.send_button.clicked.connect(self.send_home_request)
        page.stop_button.setIcon(self._icon(QStyle.StandardPixmap.SP_MediaStop))
        page.stop_button.clicked.connect(self.interrupt_home_request)
        self.history_list = page.history_list
        self.open_result_button = page.open_result_button
        self.scope_combo = page.scope_combo
        self.scope_path = page.scope_path
        self.home_conversation = page.conversation
        self.home_thinking = page.thinking
        self.home_trace = page.trace
        self.home_stage = page.stage
        self.home_input = page.input
        self.home_send_button = page.send_button
        self.home_stop_button = page.stop_button
        self.home_details_toggle = page.details_toggle
        self.home_details_panel = page.details_panel
        self.agent_input = self.home_input
        self.prompt_edit = self.home_input
        self.agent_history = self.home_conversation
        self.agent_send_button = self.home_send_button
        self.assistant_steps = self.home_stage
        return page

    def _build_plan_history_page(self) -> QWidget:
        page = PlanHistoryPage()
        page.back_button.clicked.connect(lambda: self.switch_page(0))
        page.open_button.clicked.connect(self.open_selected_plan)
        page.table.itemDoubleClicked.connect(lambda _: self.open_selected_plan())
        return page

    def _build_directory_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("accountRail")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 6, 10)

        account_group = QGroupBox("已鉴权账号")
        account_group.setObjectName("accountCard")
        account_layout = QVBoxLayout(account_group)
        account_row = QHBoxLayout()
        self.account_avatar = QLabel()
        self.account_avatar.setFixedSize(44, 44)
        self.account_avatar.setPixmap(self._icon(QStyle.StandardPixmap.SP_ComputerIcon).pixmap(40, 40))
        self.account_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        account_text = QVBoxLayout()
        self.account_name = QLabel("正在读取用户信息…")
        self.account_name.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.DemiBold))
        self.account_meta = QLabel("等待百度网盘授权")
        self.account_meta.setProperty("muted", True)
        account_text.addWidget(self.account_name)
        account_text.addWidget(self.account_meta)
        account_row.addWidget(self.account_avatar)
        account_row.addLayout(account_text, 1)
        account_layout.addLayout(account_row)
        self.quota_text = QLabel("容量：--")
        self.quota_text.setProperty("muted", True)
        self.quota_text.setWordWrap(True)
        account_layout.addWidget(self.quota_text)
        self.quota_progress = QProgressBar()
        self.quota_progress.setRange(0, 1000)
        self.quota_progress.setValue(0)
        self.quota_progress.setTextVisible(False)
        self.quota_progress.setMaximumHeight(9)
        account_layout.addWidget(self.quota_progress)
        account_actions = QHBoxLayout()
        self.reauthorize_button = QPushButton("重新授权")
        self.reauthorize_button.clicked.connect(self.reauthorize_baidu)
        self.logout_button = QPushButton("退出登录")
        self.logout_button.setProperty("danger", True)
        self.logout_button.clicked.connect(self.logout_baidu)
        account_actions.addWidget(self.reauthorize_button)
        account_actions.addWidget(self.logout_button)
        account_layout.addLayout(account_actions)
        layout.addWidget(account_group)

        title = QLabel("网盘目录")
        title.setProperty("sectionTitle", True)
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.DemiBold))
        layout.addWidget(title)
        nav = QHBoxLayout()
        up = QPushButton("上一级")
        up.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowUp))
        up.clicked.connect(self.go_up)
        self.path_edit = QLineEdit("/")
        self.path_edit.setFont(QFont("Cascadia Mono", 10))
        self.path_edit.returnPressed.connect(lambda: self.load_directory(self.path_edit.text()))
        go = QPushButton("进入")
        go.clicked.connect(lambda: self.load_directory(self.path_edit.text()))
        nav.addWidget(up)
        nav.addWidget(self.path_edit, 1)
        nav.addWidget(go)
        layout.addLayout(nav)
        self.directory_tree = QTreeWidget()
        self.directory_tree.setHeaderHidden(True)
        self.directory_tree.itemDoubleClicked.connect(self._activate_tree_item)
        layout.addWidget(self.directory_tree, 1)
        hint = QLabel("双击目录进入；常用路径在右侧快捷查看中。")
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return panel

    def _build_file_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("workspacePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 10, 6, 10)
        heading = QHBoxLayout()
        self.file_title = QLabel("文件")
        self.file_title.setProperty("sectionTitle", True)
        self.file_title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.DemiBold))
        self.file_count = QLabel("0 项")
        self.file_count.setProperty("muted", True)
        heading.addWidget(self.file_title)
        heading.addWidget(self.file_count)
        heading.addStretch(1)
        layout.addLayout(heading)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("在当前目录及子目录中搜索文件名")
        self.search_edit.returnPressed.connect(self.search_remote)
        self.search_category = QComboBox()
        for label, value in (("全部类型", 0), ("视频", 1), ("音频", 2), ("图片", 3), ("文档", 4), ("应用", 5), ("其他", 6), ("种子", 7)):
            self.search_category.addItem(label, value)
        search_button = QPushButton("搜索")
        search_button.setIcon(self._icon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        search_button.clicked.connect(self.search_remote)
        clear_button = QPushButton("清除")
        clear_button.clicked.connect(lambda: self.load_directory(self.current_path))
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_category)
        search_row.addWidget(search_button)
        search_row.addWidget(clear_button)
        layout.addLayout(search_row)

        self.file_table = QTableWidget(0, 7)
        self.file_table.setHorizontalHeaderLabels(["选", "名称", "类型", "大小", "修改时间", "路径", "原因"])
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.itemDoubleClicked.connect(self._activate_table_item)
        self.file_table.itemChanged.connect(lambda _: self._update_selection_summary())
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 38)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 220)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 70)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 88)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 140)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(6, 120)
        layout.addWidget(self.file_table, 1)

        footer = QHBoxLayout()
        select_all = QPushButton("全选")
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        invert = QPushButton("反选")
        invert.clicked.connect(self._invert_checks)
        self.selection_summary = QLabel("未选择内容")
        self.selection_summary.setProperty("muted", True)
        download = QPushButton("下载选中")
        download.setProperty("primary", True)
        download.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowDown))
        download.clicked.connect(self.download_checked)
        footer.addWidget(select_all)
        footer.addWidget(invert)
        footer.addWidget(self.selection_summary, 1)
        footer.addWidget(download)
        layout.addLayout(footer)
        return panel

    def _build_action_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("assistantPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 10, 10, 10)
        heading = QLabel("快捷查看")
        heading.setProperty("panelTitle", True)
        layout.addWidget(heading)
        self.workspace_plan_button = QPushButton("打开下载计划")
        self.workspace_plan_button.setEnabled(False)
        self.workspace_plan_button.clicked.connect(lambda: self.switch_page(2))
        layout.addWidget(self.workspace_plan_button)
        operations = QGroupBox("常用网盘操作")
        operation_layout = QGridLayout(operations)
        commands = [
            ("上传文件", self.prepare_upload_file),
            ("上传文件夹", self.prepare_upload_folder),
            ("新建文件夹", self.prepare_mkdir),
            ("移动选中", lambda: self.prepare_selected_operation("move")),
            ("复制选中", lambda: self.prepare_selected_operation("copy")),
            ("重命名", lambda: self.prepare_selected_operation("rename")),
            ("分享选中", lambda: self.prepare_selected_operation("share")),
        ]
        for index, (label, callback) in enumerate(commands):
            button = QPushButton(label)
            button.clicked.connect(callback)
            operation_layout.addWidget(button, index // 2, index % 2)
        layout.addWidget(operations)
        layout.addWidget(self._build_quick_tab(), 1)
        return panel

    def _build_plan_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("planPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        heading_row = QHBoxLayout()
        title_box = QVBoxLayout()
        heading = QLabel("下载计划详情")
        heading.setObjectName("planTitle")
        subtitle = QLabel("核对候选文件与保存位置，确认后才会开始下载。")
        subtitle.setProperty("muted", True)
        title_box.addWidget(heading)
        title_box.addWidget(subtitle)
        heading_row.addLayout(title_box, 1)
        back_button = QPushButton("返回计划列表")
        back_button.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowBack))
        back_button.clicked.connect(self.open_plan_history)
        heading_row.addWidget(back_button)
        layout.addLayout(heading_row)

        summary_band = QFrame()
        summary_band.setObjectName("planSummaryBand")
        summary_layout = QVBoxLayout(summary_band)
        self.plan_summary = QLabel("尚未生成下载计划。")
        self.plan_summary.setWordWrap(True)
        self.plan_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_layout.addWidget(self.plan_summary)
        layout.addWidget(summary_band)

        self.plan_tree = DownloadPlanTree()
        self.plan_tree.selection_changed.connect(self._update_plan_selection_summary)
        layout.addWidget(self.plan_tree, 1)

        selection_row = QHBoxLayout()
        select_all = QPushButton("全选")
        select_all.clicked.connect(lambda: self._set_plan_checks(True))
        invert = QPushButton("反选")
        invert.clicked.connect(self._invert_plan_checks)
        self.plan_selection_summary = QLabel("未选择文件")
        self.plan_selection_summary.setProperty("muted", True)
        selection_row.addWidget(select_all)
        selection_row.addWidget(invert)
        selection_row.addWidget(self.plan_selection_summary, 1)
        layout.addLayout(selection_row)

        destination_row = QHBoxLayout()
        destination_label = QLabel("保存到")
        destination_label.setProperty("muted", True)
        self.destination_edit = QLineEdit(self.config.download_root)
        browse = QPushButton("选择")
        browse.clicked.connect(self.choose_destination)
        destination_row.addWidget(destination_label)
        destination_row.addWidget(self.destination_edit, 1)
        destination_row.addWidget(browse)
        self.plan_download_button = QPushButton("确认并下载")
        self.plan_download_button.setProperty("primary", True)
        self.plan_download_button.setEnabled(False)
        self.plan_download_button.clicked.connect(self.download_plan)
        destination_row.addWidget(self.plan_download_button)
        layout.addLayout(destination_row)
        return page

    def _build_operation_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("operationPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        self.operation_title = QLabel("网盘操作计划")
        self.operation_title.setObjectName("operationTitle")
        self.operation_subtitle = QLabel("核对路径、影响范围和执行后端，确认后才会执行。")
        self.operation_subtitle.setProperty("muted", True)
        title_box.addWidget(self.operation_title)
        title_box.addWidget(self.operation_subtitle)
        heading.addLayout(title_box, 1)
        back = QPushButton("返回工作台")
        back.setIcon(self._icon(QStyle.StandardPixmap.SP_ArrowBack))
        back.clicked.connect(lambda: self.switch_page(1))
        heading.addWidget(back)
        layout.addLayout(heading)

        self.operation_backend = QLabel("尚未生成操作计划")
        self.operation_backend.setObjectName("operationBackend")
        self.operation_backend.setWordWrap(True)
        layout.addWidget(self.operation_backend)
        self.operation_details = QPlainTextEdit()
        self.operation_details.setReadOnly(True)
        self.operation_details.setFont(QFont("Cascadia Mono", 10))
        self.operation_details.setPlaceholderText("操作来源、目标和风险提示会显示在这里。")
        layout.addWidget(self.operation_details, 1)
        self.operation_result = QPlainTextEdit()
        self.operation_result.setReadOnly(True)
        self.operation_result.setMaximumHeight(150)
        self.operation_result.setPlaceholderText("执行进度与结果")
        layout.addWidget(self.operation_result)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.copy_share_button = QPushButton("复制分享信息")
        self.copy_share_button.setToolTip("复制分享链接、提取码和有效期")
        self.copy_share_button.setVisible(False)
        self.copy_share_button.setEnabled(False)
        self.copy_share_button.clicked.connect(self.copy_share_result)
        cancel = QPushButton("取消计划")
        cancel.clicked.connect(self.cancel_operation_plan)
        self.operation_confirm = QPushButton("确认并执行")
        self.operation_confirm.setProperty("primary", True)
        self.operation_confirm.setEnabled(False)
        self.operation_confirm.clicked.connect(self.execute_operation_plan)
        actions.addWidget(self.copy_share_button)
        actions.addWidget(cancel)
        actions.addWidget(self.operation_confirm)
        layout.addLayout(actions)
        return page

    def _build_quick_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        path_group = QGroupBox("快速路径")
        path_layout = QVBoxLayout(path_group)
        self.quick_path = QLineEdit("/")
        self.quick_path.setFont(QFont("Cascadia Mono", 10))
        path_layout.addWidget(self.quick_path)
        grid = QGridLayout()
        commands = [
            ("网盘根目录", lambda: self.load_directory("/")),
            ("查看该路径", lambda: self.load_directory(self.quick_path.text())),
            ("刷新当前目录", lambda: self.load_directory(self.current_path)),
            ("当前目录树", self.show_current_tree),
            ("识别章节", self.show_chapters),
            ("索引当前目录", self.index_current),
            ("导出当前清单", self.export_current),
        ]
        for index, (label, callback) in enumerate(commands):
            button = QPushButton(label)
            button.clicked.connect(callback)
            grid.addWidget(button, index // 2, index % 2)
        path_layout.addLayout(grid)
        layout.addWidget(path_group)
        output_group = QGroupBox("结构与章节")
        output_layout = QVBoxLayout(output_group)
        self.quick_output = QPlainTextEdit()
        self.quick_output.setReadOnly(True)
        self.quick_output.setFont(QFont("Cascadia Mono", 9))
        self.quick_output.setPlaceholderText("目录树、章节识别和索引结果会显示在这里。")
        output_layout.addWidget(self.quick_output)
        layout.addWidget(output_group, 1)
        return page

    def _build_task_bar(self) -> QWidget:
        bar = QWidget()
        self.task_bar = bar
        bar.setObjectName("taskDock")
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 8)
        progress_row = QHBoxLayout()
        self.task_label = QLabel("没有正在执行的下载任务")
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.pause_button = QPushButton("暂停")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setProperty("danger", True)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_download)
        progress_row.addWidget(self.task_label)
        progress_row.addWidget(self.task_progress, 1)
        progress_row.addWidget(self.pause_button)
        progress_row.addWidget(self.cancel_button)
        layout.addLayout(progress_row)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(92)
        self.log_view.setFont(QFont("Cascadia Mono", 9))
        layout.addWidget(self.log_view)
        return bar

    def _icon(self, standard: QStyle.StandardPixmap) -> QIcon:
        return self.style().standardIcon(standard)

    def _client(self, cancellation: CancellationToken | None = None) -> BaiduNetdiskClient:
        return BaiduNetdiskClient(config_store=self.store, cancellation=cancellation)

    def _run_task(
        self,
        label: str,
        function: Any,
        on_result: Any,
        on_progress: Any | None = None,
        on_error: Any | None = None,
    ) -> None:
        self.statusBar().showMessage(label)
        self._log(label)
        runner = TaskRunner(function)
        self._workers.add(runner)
        runner.signals.result.connect(on_result)
        runner.signals.error.connect(on_error or self._task_error)
        if on_progress:
            runner.signals.progress.connect(on_progress)

        def finish() -> None:
            self._workers.discard(runner)

        runner.signals.finished.connect(finish)
        self.thread_pool.start(runner)

    def _task_error(self, message: str) -> None:
        self.statusBar().showMessage("操作失败")
        self._log(f"失败：{message}")
        QMessageBox.warning(self, "操作失败", message)

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")
        log_info(message)

    def new_conversation(self) -> None:
        if self.agent_busy:
            return
        self.session_id = self.conversation_store.new_session_id()
        self.agent_history_entries.clear()
        self.home_conversation.clear()
        self.home_thinking.clear()
        self.home_trace.clear()
        self.home_stage.setText("等待提问")
        self.home_stop_button.setEnabled(False)
        self.history_list.clearSelection()
        self.home_input.setFocus()

    def _reload_conversation_list(self) -> None:
        self.history_list.clear()
        for session in self.conversation_store.sessions():
            item = QListWidgetItem(f"{session['title']}\n{session['count']} 轮")
            item.setData(Qt.ItemDataRole.UserRole, session["session_id"])
            self.history_list.addItem(item)

    def load_conversation(self, item: QListWidgetItem) -> None:
        if self.agent_busy:
            return
        session_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        turns = self.conversation_store.turns(session_id)
        if not turns:
            return
        self.session_id = session_id
        self.agent_history_entries.clear()
        self.home_conversation.clear()
        for turn in turns:
            self._append_chat_block("你", turn.request)
            self._append_chat_block("PanFetch AI", turn.response)
            self.agent_history_entries.extend((("user", turn.request), ("assistant", turn.response)))
        last = turns[-1]
        self.home_trace.setPlainText("\n".join(last.logs))
        self.home_stage.setText(f"历史记录 · {last.action} · {last.path}")

    def _scope_changed(self, _: int = -1) -> None:
        mode = str(self.scope_combo.currentData())
        self.scope_path.setEnabled(mode == "custom")
        if mode == "global":
            self.scope_path.setText("/")
        elif mode == "current":
            self.scope_path.setText(self.current_path)

    def _use_current_scope(self) -> None:
        self.scope_combo.setCurrentIndex(self.scope_combo.findData("current"))
        self.scope_path.setText(self.current_path)

    def _assistant_scope_path(self) -> tuple[str, str]:
        mode = str(self.scope_combo.currentData())
        if mode == "global":
            return mode, "/"
        value = self.current_path if mode == "current" else self.scope_path.text()
        return mode, normalize_remote_path(value)

    def send_home_request(self) -> None:
        if self.agent_busy:
            return
        request = self.home_input.toPlainText().strip()
        if not request:
            return
        try:
            scope, scope_path = self._assistant_scope_path()
        except ValueError as exc:
            QMessageBox.warning(self, "路径格式错误", str(exc))
            return
        previous_history = list(self.agent_history_entries)
        visible_paths = [item.path for item in self.current_items[:200]]
        if scope != "global":
            prefix = scope_path.rstrip("/") + "/"
            visible_paths = [path for path in visible_paths if path == scope_path or path.startswith(prefix)]
        destination = self.config.download_root
        self.agent_history_entries.append(("user", request))
        self._append_chat_block("你", request)
        self.home_input.clear()
        self.home_thinking.clear()
        self.home_trace.clear()
        self._home_logs = []
        self._home_answer_started = False
        self.agent_busy = True
        self.home_send_button.setEnabled(False)
        self.home_stop_button.setEnabled(True)
        self.home_stage.setText("正在启动编排…")
        self._home_run_id += 1
        run_id = self._home_run_id
        cancellation = CancellationToken()
        planner = LLMPlanner.from_store(self.store, cancellation)
        self._home_cancellation = cancellation
        self._home_planner = planner

        def work(progress: Any) -> AssistantRunResult:
            agent = NetdiskAgent(planner, self._client(cancellation))
            workflow = AssistantWorkflow(planner, agent)
            return workflow.run(
                request,
                scope_path,
                visible_paths,
                previous_history,
                destination,
                lambda kind, text: progress({"kind": kind, "text": text}),
                cancellation,
            )

        self._pending_home_request = (request, scope, scope_path)
        self._run_task(
            "AI 助手正在处理…",
            work,
            lambda result: self._home_ready(result) if run_id == self._home_run_id else None,
            lambda payload: self._home_progress(payload) if run_id == self._home_run_id else None,
            lambda message: self._home_error(message) if run_id == self._home_run_id else None,
        )

    def interrupt_home_request(self) -> None:
        if not self.agent_busy:
            return
        self._home_run_id += 1
        if self._home_cancellation is not None:
            self._home_cancellation.cancel()
        if self._home_planner is not None:
            self._home_planner.cancel()
        self.agent_busy = False
        self.home_send_button.setEnabled(True)
        self.home_stop_button.setEnabled(False)
        self.home_stage.setText("已中断")
        self.home_thinking.appendPlainText("\n• 已中断当前请求")
        interrupted = "已中断本次请求。"
        if self._home_answer_started:
            self.home_conversation.append_stream_text("\n\n[回答已中断]", status=True)
        else:
            self._append_chat_block("PanFetch AI", interrupted)
        self.agent_history_entries.append(("assistant", interrupted))
        if hasattr(self, "_pending_home_request"):
            request, scope, scope_path = self._pending_home_request
            logs = [*self._home_logs, "用户中断当前 AI 请求"]
            self.conversation_store.append(
                self.session_id,
                request,
                interrupted,
                scope,
                scope_path,
                "cancelled",
                logs,
            )
            self._reload_conversation_list()
        self._home_cancellation = None
        self._home_planner = None
        self.statusBar().showMessage("AI 请求已中断")
        self.home_input.setFocus()

    def _home_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        kind = str(payload.get("kind") or "")
        text = str(payload.get("text") or "")
        if not text:
            return
        if kind == "stage":
            self.home_stage.setText(text)
            self.home_thinking.appendPlainText(f"• {text}")
            self.home_thinking.ensureCursorVisible()
        elif kind == "log":
            self._home_logs.append(text)
            self.home_trace.appendPlainText(text)
        elif kind == "thinking":
            self.home_thinking.moveCursor(QTextCursor.MoveOperation.End)
            self.home_thinking.insertPlainText(text)
            self.home_thinking.ensureCursorVisible()
        elif kind == "answer":
            if not self._home_answer_started:
                self._append_chat_block("PanFetch AI", "")
                self._home_answer_started = True
            self.home_conversation.append_stream_text(text)

    def _home_ready(self, workflow_result: AssistantRunResult) -> None:
        self.agent_busy = False
        self.home_send_button.setEnabled(True)
        self.home_stop_button.setEnabled(False)
        self._home_cancellation = None
        self._home_planner = None
        if not self._home_answer_started:
            self._append_chat_block("PanFetch AI", workflow_result.answer)
        self.agent_history_entries.append(("assistant", workflow_result.answer))
        request, scope, scope_path = self._pending_home_request
        logs = self._home_logs or workflow_result.logs
        self.conversation_store.append(
            self.session_id,
            request,
            workflow_result.answer,
            scope,
            scope_path,
            workflow_result.action,
            logs,
        )
        self._reload_conversation_list()
        result = workflow_result.result
        if result.items:
            self.catalog.upsert(result.items)
        if result.preview is not None:
            self._plan_ready(result.preview, request=request)
        elif result.operation is not None:
            self._show_operation_plan(result.operation)
        elif result.items:
            self.current_items = result.items
            if result.path:
                self.current_path = result.path
                self.path_edit.setText(result.path)
                self.quick_path.setText(result.path)
            self.file_title.setText(f"AI 助手 · {result.action}")
            self._fill_table(result.items, "助手结果")
            if result.action in {"list", "chapters"}:
                self._fill_tree(result.path or self.current_path, result.items)
            if result.action in {"tree", "chapters", "inspect"}:
                self.quick_output.setPlainText(result.message)
        self.home_stage.setText(f"完成 · {workflow_result.action}")
        self.statusBar().showMessage("AI 助手已完成")

    def _show_operation_plan(self, plan: OperationPlan) -> None:
        self.current_operation = plan
        self.operation_title.setText(plan.title)
        backend_labels = {
            "openapi": "百度网盘 OpenAPI",
            "mcp": "百度官方 MCP（全盘分享）",
            "bdpan": "bdpan Skill（分享链接转存/下载）",
        }
        backend = backend_labels.get(plan.backend, plan.backend)
        available = True
        detail = backend
        if plan.backend == "bdpan":
            status = BdpanBackend().status()
            available = status.available
            detail = f"执行后端：{backend}\n{status.detail}"
        elif plan.backend == "mcp":
            detail = f"执行后端：{backend}\n使用当前百度 OAuth 授权，不依赖 bdpan。"
        else:
            detail = f"执行后端：{backend}"
        self.operation_backend.setText(detail)
        self.operation_backend.setProperty("state", "success" if available else "error")
        self.operation_backend.style().unpolish(self.operation_backend)
        self.operation_backend.style().polish(self.operation_backend)
        warnings = "\n".join(f"注意：{item}" for item in plan.warnings)
        self.operation_details.setPlainText(plan.summary + (f"\n\n{warnings}" if warnings else ""))
        self.operation_result.clear()
        self._share_copy_text = ""
        self.copy_share_button.setVisible(plan.action == "share")
        self.copy_share_button.setEnabled(False)
        self.operation_confirm.setEnabled(available)
        self.operation_confirm.setText("确认并执行")
        self.switch_page(3)

    def cancel_operation_plan(self) -> None:
        self.current_operation = None
        self._share_copy_text = ""
        self.copy_share_button.setEnabled(False)
        self.operation_confirm.setEnabled(False)
        self.operation_result.setPlainText("操作计划已取消，未执行任何写入。")
        self.statusBar().showMessage("操作计划已取消")

    def execute_operation_plan(self) -> None:
        plan = self.current_operation
        if plan is None:
            return
        answer = QMessageBox.question(
            self,
            "确认执行网盘操作",
            f"{plan.summary}\n\n确认执行后将产生实际变更。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.operation_confirm.setEnabled(False)
        self.operation_result.setPlainText("正在执行…")
        self._share_copy_text = ""
        self.copy_share_button.setEnabled(False)

        def work(progress: Any) -> OperationResult:
            return NetdiskOperationExecutor(self._client()).execute(plan, progress)

        self._run_task(
            f"正在执行：{plan.title}",
            work,
            self._operation_ready,
            self._operation_progress,
            self._operation_error,
        )

    def _operation_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        stage = str(payload.get("stage") or "执行")
        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        path = str(payload.get("path") or "")
        line = f"{stage} {current}/{total} {path}" if total else f"{stage} {path}"
        self.operation_result.appendPlainText(line)

    def _operation_ready(self, result: OperationResult) -> None:
        self.operation_result.appendPlainText(result.message)
        self.quick_output.setPlainText(result.message)
        if result.action == "share" and self.current_operation is not None:
            self._share_copy_text = format_share_copy_text(result, self.current_operation)
            self.copy_share_button.setEnabled(bool(self._share_copy_text))
        self.current_operation = None
        self.operation_confirm.setText("执行完成")
        self.operation_confirm.setEnabled(False)
        self.statusBar().showMessage(result.message.splitlines()[0])
        if result.action in {"upload", "move", "copy", "rename", "mkdir", "transfer"}:
            self.load_directory(self.current_path)

    def copy_share_result(self) -> None:
        if not self._share_copy_text:
            return
        QApplication.clipboard().setText(self._share_copy_text)
        self.statusBar().showMessage("分享链接、提取码和有效期已复制")

    def _operation_error(self, message: str) -> None:
        self.operation_result.appendPlainText(f"执行失败：{message}")
        self.operation_confirm.setEnabled(self.current_operation is not None)
        self.operation_confirm.setText("重新执行")
        self._task_error(message)

    def open_latest_result(self) -> None:
        self.open_plan_history()

    def open_plan_history(self) -> None:
        self._reload_plan_history()
        self.switch_page(4)

    def _reload_plan_history(self) -> None:
        if hasattr(self, "plan_history_page"):
            self.plan_history_page.populate(self.plan_history_store.summaries())

    def open_selected_plan(self) -> None:
        if self.plan_history_page.is_loading:
            return
        record_id = self.plan_history_page.selected_record_id()
        if not record_id:
            return
        self.plan_history_page.set_loading(True)

        def ready(record: PlanHistoryRecord | None) -> None:
            self.plan_history_page.set_loading(False)
            if record is None:
                QMessageBox.warning(self, "计划无法读取", "该历史计划不存在或本地记录已损坏。")
                self._reload_plan_history()
                return
            self._show_plan_preview(record)
            self.switch_page(2)
            self.statusBar().showMessage("计划详情已加载")

        def failed(message: str) -> None:
            self.plan_history_page.set_loading(False)
            self._task_error(message)

        self._run_task(
            "正在读取计划详情…",
            lambda _: self.plan_history_store.get(record_id),
            ready,
            on_error=failed,
        )

    def _home_error(self, message: str) -> None:
        self.agent_busy = False
        self.home_send_button.setEnabled(True)
        self.home_stop_button.setEnabled(False)
        self._home_cancellation = None
        self._home_planner = None
        self.home_stage.setText("执行失败")
        self.home_trace.appendPlainText(message)
        failure = f"操作失败：{message}"
        self._append_chat_block("PanFetch AI", failure)
        self.agent_history_entries.append(("assistant", failure))
        if hasattr(self, "_pending_home_request"):
            request, scope, scope_path = self._pending_home_request
            self.conversation_store.append(
                self.session_id,
                request,
                failure,
                scope,
                scope_path,
                "error",
                [*self._home_logs, message],
            )
            self._reload_conversation_list()
        self._task_error(message)

    def _append_chat_block(self, speaker: str, text: str) -> None:
        self.home_conversation.append_message("user" if speaker == "你" else "assistant", text)

    def check_connection(self) -> None:
        if not self.store.has_baidu_token():
            self._reset_account_view()
            self._set_connection("未配置百度授权", False)
            return

        def work(_: Any) -> tuple[dict[str, Any], dict[str, Any], bytes]:
            client = self._client()
            account = client.account_info()
            try:
                quota = client.quota_info()
            except NetdiskError:
                quota = {}
            avatar = client.avatar_bytes(str(account.get("avatar_url") or ""))
            return account, quota, avatar

        self._run_task("正在检查百度网盘连接…", work, self._connection_ready)

    def show_connection_status(self) -> None:
        def work(_: Any) -> dict[str, Any]:
            result: dict[str, Any] = {
                "baidu_ok": False,
                "baidu_detail": "未配置授权",
                "llm_ok": False,
                "llm_detail": "未配置 LLM",
                "share_ok": False,
                "share_detail": "未配置百度授权",
                "bdpan_ok": False,
                "bdpan_detail": "未检测",
            }
            if self.store.has_baidu_token():
                try:
                    client = self._client()
                    account = client.account_info()
                    try:
                        quota = client.quota_info()
                    except NetdiskError:
                        quota = {}
                    avatar = client.avatar_bytes(str(account.get("avatar_url") or ""))
                    result.update(
                        baidu_ok=True,
                        baidu_detail=f"已连接：{account.get('netdisk_name') or account.get('baidu_name') or '已授权账号'}",
                        account=account,
                        quota=quota,
                        avatar=avatar,
                    )
                    try:
                        result["share_ok"] = client.share_available()
                        result["share_detail"] = "百度官方 MCP 全盘分享服务可用"
                    except Exception:
                        result["share_detail"] = "官方 MCP 分享服务连接失败，请检查授权或网络"
                except Exception:
                    result["baidu_detail"] = "连接失败，请重新授权或检查网络"

            planner = LLMPlanner.from_store(self.store)
            if planner.configured:
                try:
                    reply = planner.test_connection()
                    result.update(
                        llm_ok=True,
                        llm_detail=f"已连接：{planner.config.model} · {reply[:30] or '响应正常'}",
                    )
                except Exception:
                    result["llm_detail"] = f"连接失败：{planner.config.model}，请检查模型、API Key 和网络"
            bdpan = BdpanBackend().status()
            result["bdpan_ok"] = bdpan.available
            result["bdpan_detail"] = bdpan.detail
            return result

        self._run_task("正在检查百度网盘与 LLM 连接…", work, self._connection_status_ready)

    def _connection_status_ready(self, result: dict[str, Any]) -> None:
        if result.get("baidu_ok"):
            self._connection_ready((result["account"], result["quota"], result["avatar"]))
        else:
            self._reset_account_view()
            self._set_connection(str(result.get("baidu_detail") or "连接失败"), False)
        baidu_mark = "正常" if result.get("baidu_ok") else "异常"
        llm_mark = "正常" if result.get("llm_ok") else "异常"
        share_mark = "可用" if result.get("share_ok") else "不可用"
        bdpan_mark = "可用" if result.get("bdpan_ok") else "未配置（可选）"
        box = QMessageBox(self)
        box.setWindowTitle("连接状态")
        box.setIcon(
            QMessageBox.Icon.Information
            if result.get("baidu_ok") and result.get("llm_ok") and result.get("share_ok")
            else QMessageBox.Icon.Warning
        )
        box.setText(
            f"百度网盘：{baidu_mark}\n{result.get('baidu_detail')}\n\n"
            f"LLM：{llm_mark}\n{result.get('llm_detail')}\n\n"
            f"全盘分享：{share_mark}\n{result.get('share_detail')}\n\n"
            f"分享链接转存/下载：{bdpan_mark}\n{result.get('bdpan_detail')}"
        )
        box.exec()

    def _connection_ready(self, result: tuple[dict[str, Any], dict[str, Any], bytes]) -> None:
        account, quota, avatar = result
        name = account.get("netdisk_name") or account.get("baidu_name") or "已授权账号"
        vip = int(account.get("vip_type") or 0)
        membership = "SVIP" if vip == 2 else "VIP" if vip == 1 else "普通用户"
        suffix = f" · {membership}"
        uk = account.get("uk")
        self.account_name.setText(str(name))
        self.account_meta.setText(f"{membership} · UID {uk}" if uk is not None else membership)

        total = max(0, int(quota.get("total") or 0))
        used = max(0, int(quota.get("used") or 0))
        remaining = max(0, total - used)
        if total:
            self.quota_text.setText(f"已用 {format_size(used)} / {format_size(total)}\n剩余 {format_size(remaining)}")
            self.quota_progress.setValue(min(1000, round(used * 1000 / total)))
        else:
            self.quota_text.setText("容量信息暂不可用")
            self.quota_progress.setValue(0)
        if quota.get("expire"):
            self.quota_text.setToolTip("部分容量将在 7 天内到期")
        if avatar:
            pixmap = QPixmap()
            if pixmap.loadFromData(avatar):
                self.account_avatar.setPixmap(
                    pixmap.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        self._set_connection(f"{name}{suffix}", True)
        self.logout_button.setEnabled(True)
        self.load_directory(self.current_path)

    def _reset_account_view(self) -> None:
        self.account_name.setText("未登录百度网盘")
        self.account_meta.setText("授权后自动显示账号信息")
        self.quota_text.setText("容量：--")
        self.quota_progress.setValue(0)
        self.account_avatar.setPixmap(self._icon(QStyle.StandardPixmap.SP_ComputerIcon).pixmap(40, 40))
        self.logout_button.setEnabled(False)

    def reauthorize_baidu(self) -> None:
        self.open_settings("baidu")

    def logout_baidu(self) -> None:
        answer = QMessageBox.question(
            self,
            "退出百度网盘",
            "这会删除本机加密保存的百度 Access Token，不会影响网盘中的任何文件。确定退出吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        used_environment = self.store.delete_baidu_token()
        self._reset_account_view()
        self.current_items = []
        self.current_plan = None
        self.current_preview = None
        self.workspace_plan_button.setEnabled(False)
        self.plan_download_button.setEnabled(False)
        self.plan_tree.clear()
        self.plan_summary.setText("尚未生成下载计划。")
        self.directory_tree.clear()
        self._fill_table([])
        self._set_connection("已退出百度网盘", False)
        self._log("已退出百度网盘并清除本机加密授权")
        if used_environment:
            QMessageBox.information(
                self,
                "已退出当前会话",
                "当前进程中的环境变量授权已清除。若系统环境变量仍保存 Token，下次启动时需要同时移除该环境变量。",
            )

    def _set_connection(self, text: str, connected: bool) -> None:
        self.connection_label.setText(text)
        self.connection_label.setProperty("status", "connected" if connected else "error")
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)
        self.statusBar().showMessage(text)

    def load_directory(self, path: str) -> None:
        try:
            normalized = normalize_remote_path(path)
        except ValueError as exc:
            self._task_error(str(exc))
            return

        def work(_: Any) -> tuple[str, list[RemoteItem]]:
            items = self._client().list_directory(normalized)
            self.catalog.upsert(items)
            return normalized, items

        self._run_task(f"正在读取 {normalized}", work, self._directory_ready)

    def _directory_ready(self, result: tuple[str, list[RemoteItem]]) -> None:
        path, items = result
        self.current_path = path
        self.current_items = items
        self.path_edit.setText(path)
        self.quick_path.setText(path)
        self.file_title.setText(path)
        self._fill_table(items)
        self._fill_tree(path, items)
        self.statusBar().showMessage(f"已读取 {path}：{len(items)} 项")
        self._log(f"目录读取完成：{path}，{len(items)} 项")

    def _fill_tree(self, path: str, items: list[RemoteItem]) -> None:
        self.directory_tree.clear()
        root = QTreeWidgetItem([path])
        root.setData(0, Qt.ItemDataRole.UserRole, path)
        root.setIcon(0, self._icon(QStyle.StandardPixmap.SP_DirHomeIcon))
        self.directory_tree.addTopLevelItem(root)
        for item in items:
            if not item.is_dir:
                continue
            child = QTreeWidgetItem([item.name])
            child.setData(0, Qt.ItemDataRole.UserRole, item.path)
            child.setIcon(0, self._icon(QStyle.StandardPixmap.SP_DirIcon))
            root.addChild(child)
        root.setExpanded(True)

    def _fill_table(self, items: list[RemoteItem], reason: str = "") -> None:
        self.file_table.blockSignals(True)
        self.file_table.setSortingEnabled(False)
        self.file_table.setRowCount(len(items))
        for row, remote in enumerate(items):
            check = QTableWidgetItem()
            check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            name = QTableWidgetItem(remote.name)
            name.setData(Qt.ItemDataRole.UserRole, remote)
            name.setIcon(self._icon(QStyle.StandardPixmap.SP_DirIcon if remote.is_dir else QStyle.StandardPixmap.SP_FileIcon))
            type_item = QTableWidgetItem("目录" if remote.is_dir else (Path(remote.name).suffix.lower() or "文件"))
            size = QTableWidgetItem("-" if remote.is_dir else format_size(remote.size))
            modified = QTableWidgetItem(format_time(remote.modified))
            path_item = QTableWidgetItem(remote.path)
            path_item.setFont(QFont("Cascadia Mono", 9))
            reason_item = QTableWidgetItem("" if remote.is_dir else reason)
            if reason:
                reason_item.setForeground(QColor("#55D69A"))
            for column, cell in enumerate((check, name, type_item, size, modified, path_item, reason_item)):
                self.file_table.setItem(row, column, cell)
        self.file_count.setText(f"{len(items)} 项")
        self.file_table.setSortingEnabled(True)
        self.file_table.blockSignals(False)
        self._update_selection_summary()

    def _activate_tree_item(self, item: QTreeWidgetItem) -> None:
        path = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if path:
            self.load_directory(path)

    def _activate_table_item(self, item: QTableWidgetItem) -> None:
        remote = self.file_table.item(item.row(), 1).data(Qt.ItemDataRole.UserRole)
        if isinstance(remote, RemoteItem) and remote.is_dir:
            self.load_directory(remote.path)

    def go_up(self) -> None:
        if self.current_path == "/":
            return
        parent = str(Path(self.current_path.replace("/", os.sep)).parent).replace(os.sep, "/")
        self.load_directory(parent if parent.startswith("/") else f"/{parent}")

    def search_remote(self) -> None:
        keyword = self.search_edit.text().strip()
        category = int(self.search_category.currentData() or 0)
        if not keyword and not category:
            self.load_directory(self.current_path)
            return

        def work(_: Any) -> list[RemoteItem]:
            client = self._client()
            if keyword:
                items = client.search(keyword, self.current_path, recursive=True, limit=500, category=category)
            else:
                items = [item for item in client.walk(self.current_path, max_depth=-1, limit=2500) if matches_category(item, category)][:500]
            self.catalog.upsert(items)
            return items

        def ready(items: list[RemoteItem]) -> None:
            self.current_items = items
            self._fill_table(items, "搜索命中")
            label = keyword or self.search_category.currentText()
            self.file_title.setText(f"搜索：{label}")
            self.statusBar().showMessage(f"找到 {len(items)} 项")

        self._run_task(f"正在搜索：{keyword or self.search_category.currentText()}", work, ready)

    def prepare_upload_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择要上传的文件")
        if path:
            self._prepare_direct_operation("upload", {"local_path": path, "remote_path": self.current_path}, "工作台上传文件")

    def prepare_upload_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择要上传的文件夹")
        if path:
            self._prepare_direct_operation("upload", {"local_path": path, "remote_path": self.current_path}, "工作台上传文件夹")

    def prepare_mkdir(self) -> None:
        name, accepted = QInputDialog.getText(self, "新建网盘文件夹", "文件夹名称或绝对网盘路径：")
        if not accepted or not name.strip():
            return
        value = name.strip()
        path = value if value.startswith("/") else f"{self.current_path.rstrip('/')}/{value}"
        self._prepare_direct_operation("mkdir", {"path": path}, "工作台新建文件夹")

    def prepare_selected_operation(self, action: str) -> None:
        selected = self._checked_items()
        if not selected:
            QMessageBox.information(self, "没有选中内容", "请先勾选需要操作的文件或文件夹。")
            return
        if action == "share":
            period_label, accepted = QInputDialog.getItem(
                self,
                "分享有效期",
                "选择分享链接有效期：",
                ["7 天", "1 天", "30 天", "永久"],
                0,
                False,
            )
            if accepted:
                periods = {"永久": 0, "1 天": 1, "7 天": 7, "30 天": 30}
                self._prepare_direct_operation(
                    "share",
                    {"paths": [item.path for item in selected], "period": periods[period_label]},
                    "工作台生成分享链接",
                )
            return
        if len(selected) != 1:
            QMessageBox.information(self, "一次选择一项", "移动、复制和重命名一次只能处理一个文件或文件夹。")
            return
        source = selected[0]
        if action in {"move", "copy"}:
            destination, accepted = QInputDialog.getText(
                self,
                "移动到" if action == "move" else "复制到",
                "目标网盘目录：",
                text=self.current_path,
            )
            if accepted and destination.strip():
                self._prepare_direct_operation(action, {"source": source.path, "destination": destination.strip()}, f"工作台{action}")
        elif action == "rename":
            new_name, accepted = QInputDialog.getText(self, "重命名", "新名称：", text=source.name)
            if accepted and new_name.strip():
                self._prepare_direct_operation("rename", {"path": source.path, "new_name": new_name.strip()}, "工作台重命名")

    def _prepare_direct_operation(self, action: str, arguments: dict[str, Any], request: str) -> None:
        try:
            plan = build_operation_plan(action, arguments, request)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "无法生成操作计划", str(exc))
            return
        self._show_operation_plan(plan)

    def generate_plan(self) -> None:
        request = self.prompt_edit.toPlainText().strip()
        if not request:
            QMessageBox.information(self, "请输入诉求", "请先描述需要查找、下载和整理的内容。")
            return
        context_paths = [item.path for item in self.current_items[:200]]
        destination = self.destination_edit.text().strip() or self.config.download_root

        def work(progress: Any) -> PlanPreview:
            planner = LLMPlanner.from_store(self.store)
            plan = planner.create_plan(request, context_paths, destination, self.current_path)
            client = self._client()
            by_id: dict[int, RemoteItem] = {}
            for source in plan.source_paths:
                scanned = client.walk(source, max_depth=-1, limit=0, progress=lambda path, count: progress({"path": path, "count": count}))
                for remote in scanned:
                    by_id[remote.fs_id] = remote
            all_items = list(by_id.values())
            self.catalog.upsert(all_items)
            return build_preview(plan, all_items)

        self.assistant_steps.setText("✓ 理解请求    ● 扫描目录    ○ 生成计划    ○ 等待确认")
        self._run_task(
            "AI 正在生成并验证下载计划…",
            work,
            lambda preview: self._plan_ready(preview, request=request),
            self._plan_progress,
        )

    def _plan_progress(self, payload: object) -> None:
        if isinstance(payload, dict):
            self.statusBar().showMessage(f"扫描 {payload.get('path')} · 已发现 {payload.get('count')} 项")

    def _plan_ready(self, preview: PlanPreview, request: str = "", *, record_history: bool = True) -> None:
        plan = replace(preview.plan, destination=preview.plan.destination or self.config.download_root)
        preview = replace(preview, plan=plan)
        record = PlanHistoryRecord(
            summary=self._temporary_plan_summary(request, preview),
            preview=preview,
        )
        if record_history:
            try:
                record = self.plan_history_store.save(request, preview)
                self._reload_plan_history()
            except (OSError, sqlite3.Error, ValueError) as exc:
                self._log(f"计划历史保存失败：{exc}")
        self._show_plan_preview(record)
        self.assistant_steps.setText("✓ 理解请求    ✓ 扫描目录    ✓ 生成计划    ● 等待确认")
        self.statusBar().showMessage("下载计划已生成，可在计划列表中随时查看")
        self._log(f"计划生成：选择 {len(preview.selected)} 个文件，排除 {preview.excluded_count} 项")

    def _show_plan_preview(self, record: PlanHistoryRecord) -> None:
        preview = record.preview
        plan = preview.plan
        self.current_plan = plan
        self.current_preview = preview
        self.destination_edit.setText(plan.destination)
        self.current_items = preview.selected
        self._fill_plan_tree(preview.selected)
        self.plan_download_button.setEnabled(bool(preview.selected))
        excluded = "、".join(f"{name} {count}" for name, count in preview.excluded_reasons.items()) or "无"
        source_lines = [f"• {path}" for path in plan.source_paths[:6]]
        if len(plan.source_paths) > 6:
            source_lines.append(f"• 另有 {len(plan.source_paths) - 6} 个来源路径")
        sources = "\n".join(source_lines)
        includes = "、".join([*plan.include_keywords, *plan.include_extensions]) or "全部文件"
        excludes = "、".join([*plan.exclude_keywords, *plan.exclude_extensions]) or "无"
        self.plan_summary.setText(
            f"需求：{record.summary.request}\n"
            f"生成时间：{_format_plan_timestamp(record.summary.created_at)}\n\n"
            f"来源路径\n{sources}\n\n"
            f"候选：{len(preview.selected)} 个文件 · {format_size(preview.total_bytes)}    "
            f"包含：{includes}    排除条件：{excludes}\n"
            f"规则结果：排除 {preview.excluded_count} 项（{excluded}）    "
            f"整理：{organize_label(plan.organize_by)}\n"
            f"说明：{plan.reasoning or '已按结构化规则生成候选。'}"
        )
        self.workspace_plan_button.setEnabled(True)

    @staticmethod
    def _temporary_plan_summary(request: str, preview: PlanPreview) -> PlanHistorySummary:
        return PlanHistorySummary(
            record_id="",
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            request=request.strip() or preview.plan.reasoning or "下载计划",
            source_paths=list(preview.plan.source_paths),
            file_count=len(preview.selected),
            total_bytes=preview.total_bytes,
            destination=preview.plan.destination,
        )

    def check_llm(self) -> None:
        def work(_: Any) -> str:
            planner = LLMPlanner.from_store(self.store)
            if not planner.configured:
                raise ValueError("尚未配置 LLM Base URL 和模型")
            return planner.test_connection()

        def ready(reply: str) -> None:
            configured = self.store.load().llm.model
            detail = f"对话接口连接正常；当前模型：{configured}；回复：{reply[:40] or '成功'}"
            self.statusBar().showMessage(detail)
            self._log(detail)
            QMessageBox.information(self, "LLM 连接正常", detail)

        self._run_task("正在检查 LLM 接口…", work, ready)

    def send_agent_request(self) -> None:
        self.send_home_request()

    def clear_agent_history(self) -> None:
        self.new_conversation()

    def show_current_tree(self) -> None:
        path = normalize_remote_path(self.quick_path.text() or self.current_path)

        def work(progress: Any) -> tuple[list[RemoteItem], str]:
            items = self._client().walk(path, max_depth=3, limit=2000, progress=lambda current, count: progress({"path": current, "count": count}))
            self.catalog.upsert(items)
            return items, tree_text(path, items)

        def ready(result: tuple[list[RemoteItem], str]) -> None:
            _, text = result
            self.quick_output.setPlainText(text)
            self.statusBar().showMessage("目录结构已读取")

        self._run_task(f"正在读取 {path} 的三层结构…", work, ready, self._plan_progress)

    def show_chapters(self) -> None:
        path = normalize_remote_path(self.quick_path.text() or self.current_path)

        def work(_: Any) -> tuple[list[RemoteItem], str]:
            items = self._client().list_directory(path)
            self.catalog.upsert(items)
            return items, "\n".join(chapter_lines(path, items))

        def ready(result: tuple[list[RemoteItem], str]) -> None:
            _, text = result
            self.quick_output.setPlainText(text)
            self.statusBar().showMessage("章节识别完成")

        self._run_task(f"正在识别 {path} 的章节…", work, ready)

    def index_current(self) -> None:
        path = normalize_remote_path(self.quick_path.text() or self.current_path)

        def work(progress: Any) -> int:
            items = self._client().walk(path, max_depth=-1, limit=0, progress=lambda current, count: progress({"path": current, "count": count}))
            return self.catalog.upsert(items)

        def ready(count: int) -> None:
            stats = self.catalog.stats()
            self.quick_output.setPlainText(
                f"本次索引：{count} 项\n索引总量：{stats['total']} 项\n目录：{stats['dirs']} 个\n文件体积：{format_size(stats['bytes'])}"
            )
            self.statusBar().showMessage(f"索引完成：{count} 项")

        self._run_task(f"正在索引 {path}…", work, ready, self._plan_progress)

    def export_current(self) -> None:
        if not self.current_items:
            QMessageBox.information(self, "没有可导出内容", "请先读取一个目录或执行搜索。")
            return
        default_name = f"PanFetch-AI-{self.current_path.strip('/').replace('/', '-') or 'root'}.csv"
        selected, _ = QFileDialog.getSaveFileName(self, "导出当前清单", str(Path.cwd() / default_name), "CSV 文件 (*.csv)")
        if not selected:
            return
        Path(selected).write_text(items_to_csv(self.current_items), encoding="utf-8-sig")
        self._log(f"已导出：{selected}")
        self.statusBar().showMessage(f"已导出 {len(self.current_items)} 项")

    def choose_destination(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择下载位置",
            self.destination_edit.text() or self.config.download_root,
        )
        if selected:
            self.destination_edit.setText(selected)

    def _fill_plan_tree(self, items: list[RemoteItem]) -> None:
        self.plan_tree.set_items(items)

    def _checked_plan_items(self) -> list[RemoteItem]:
        return self.plan_tree.checked_items()

    def _set_plan_checks(self, checked: bool) -> None:
        self.plan_tree.set_all_checked(checked)

    def _invert_plan_checks(self) -> None:
        self.plan_tree.invert_checks()

    def _update_plan_selection_summary(self) -> None:
        selected = self._checked_plan_items()
        self.plan_selection_summary.setText(
            f"已选择 {len(selected)} 个文件 · {format_size(sum(item.size for item in selected))}"
            if selected
            else "未选择文件"
        )
        self.plan_download_button.setEnabled(bool(selected) and self.current_plan is not None)

    def download_plan(self) -> None:
        if self.current_plan is None:
            QMessageBox.information(self, "没有下载计划", "请先在 AI 问答页面向助手提出下载要求。")
            return
        selected = self._checked_plan_items()
        if not selected:
            QMessageBox.information(self, "没有选中文件", "请至少选择一个候选文件。")
            return
        destination = self.destination_edit.text().strip() or self.config.download_root
        if not Path(destination).is_absolute():
            QMessageBox.warning(self, "保存位置无效", "请选择一个本地绝对路径。")
            return
        plan = replace(self.current_plan, destination=destination)
        self.current_plan = plan
        self._confirm_download(selected, plan, selected)

    def download_checked(self) -> None:
        if self.download_running:
            QMessageBox.information(self, "下载进行中", "请先完成或取消当前下载任务。")
            return
        selected = self._checked_items()
        if not selected:
            QMessageBox.information(self, "没有选中内容", "请勾选需要下载的文件或文件夹。")
            return
        destination = QFileDialog.getExistingDirectory(self, "选择下载位置", self.config.download_root)
        if not destination:
            return
        plan = SelectionPlan(source_paths=[self.current_path], destination=destination)

        directories = [item for item in selected if item.is_dir]
        if not directories:
            self._confirm_download(selected, plan, selected)
            return

        def work(progress: Any) -> list[RemoteItem]:
            return expand_selected_items(self._client(), selected, progress)

        self._run_task(
            f"正在展开 {len(directories)} 个文件夹…",
            work,
            lambda files: self._confirm_download(files, plan, selected),
            self._plan_progress,
        )

    def _confirm_download(
        self,
        files: list[RemoteItem],
        plan: SelectionPlan,
        selected_roots: list[RemoteItem],
    ) -> None:
        files = list({item.fs_id or item.path: item for item in files if not item.is_dir}.values())
        if not files:
            QMessageBox.information(self, "没有可下载文件", "选中的文件夹中没有找到文件。")
            return
        total_bytes = sum(item.size for item in files)
        excluded = "无"
        if self.current_preview and self.current_preview.excluded_reasons:
            excluded = "、".join(f"{name} {count}" for name, count in self.current_preview.excluded_reasons.items())
        preview_names = download_preview_tree(files, selected_roots)
        folder_count = sum(item.is_dir for item in selected_roots)
        root_summary = f"（由 {folder_count} 个文件夹递归展开）" if folder_count else ""
        answer = QMessageBox.question(
            self,
            "确认下载计划",
            f"来源：{'、'.join(plan.source_paths)}\n"
            f"保存到：{plan.destination}\n"
            f"文件：{len(files)} 个{root_summary}，共 {format_size(total_bytes)}\n"
            f"整理：{organize_label(plan.organize_by)}\n"
            f"排除：{excluded}\n\n"
            f"下载内容预览：\n{preview_names}\n\n确认后才会开始下载。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.assistant_steps.setText("✓ 理解请求    ✓ 扫描目录    ✓ 生成计划    ✓ 已确认下载")
        self._start_download(files, plan)

    def _start_download(self, items: list[RemoteItem], plan: SelectionPlan) -> None:
        self.download_control = DownloadControl()
        self.download_running = True
        self.task_bar.setVisible(True)
        self.download_paused = False
        self.pause_button.setText("暂停")
        self.pause_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.task_progress.setValue(0)
        self.task_label.setText(f"正在下载 0/{len(items)}")

        def work(progress: Any) -> list[Any]:
            manager = DownloadManager(self._client(), self.store.load().concurrency)
            return manager.download(
                items,
                plan,
                progress=lambda completed, total, result: progress({"completed": completed, "total": total, "result": result}),
                control=self.download_control,
            )

        self._run_task("下载任务已开始", work, self._download_ready, self._download_progress)

    def _download_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        completed = int(payload["completed"])
        total = int(payload["total"])
        result = payload["result"]
        self.task_progress.setValue(int(completed * 100 / max(total, 1)))
        self.task_label.setText(f"正在下载 {completed}/{total}")
        self._log(f"{result.status}: {result.remote_path}")

    def _download_ready(self, results: list[Any]) -> None:
        self.download_running = False
        self.pause_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        downloaded = sum(item.status == "downloaded" for item in results)
        skipped = sum(item.status == "skipped" for item in results)
        failed = sum(item.status == "failed" for item in results)
        cancelled = sum(item.status == "cancelled" for item in results)
        self.task_progress.setValue(100 if not cancelled else self.task_progress.value())
        self.task_label.setText(f"完成：下载 {downloaded}，跳过 {skipped}，失败 {failed}，取消 {cancelled}")
        self._log(self.task_label.text())
        QMessageBox.information(self, "下载任务结束", self.task_label.text())

    def toggle_pause(self) -> None:
        if not self.download_control:
            return
        if self.download_paused:
            self.download_control.resume()
            self.download_paused = False
            self.pause_button.setText("暂停")
            self.task_label.setText("下载已继续")
        else:
            self.download_control.pause()
            self.download_paused = True
            self.pause_button.setText("继续")
            self.task_label.setText("等待当前文件完成后暂停")

    def cancel_download(self) -> None:
        if self.download_control:
            self.download_control.cancel()
            self.task_label.setText("正在取消…")
            self.cancel_button.setEnabled(False)

    def _checked_items(self) -> list[RemoteItem]:
        selected: list[RemoteItem] = []
        for row in range(self.file_table.rowCount()):
            check = self.file_table.item(row, 0)
            remote = self.file_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            if check.checkState() == Qt.CheckState.Checked and isinstance(remote, RemoteItem):
                selected.append(remote)
        return selected

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.file_table.rowCount()):
            check = self.file_table.item(row, 0)
            remote = self.file_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            if isinstance(remote, RemoteItem):
                check.setCheckState(state)
        self._update_selection_summary()

    def _invert_checks(self) -> None:
        for row in range(self.file_table.rowCount()):
            check = self.file_table.item(row, 0)
            remote = self.file_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            if isinstance(remote, RemoteItem):
                check.setCheckState(Qt.CheckState.Unchecked if check.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        selected = self._checked_items()
        files = [item for item in selected if not item.is_dir]
        folders = [item for item in selected if item.is_dir]
        if not selected:
            self.selection_summary.setText("未选择内容")
            return
        parts = []
        if folders:
            parts.append(f"{len(folders)} 个文件夹")
        if files:
            parts.append(f"{len(files)} 个文件 · {format_size(sum(item.size for item in files))}")
        self.selection_summary.setText("已选择 " + "，".join(parts))

    def open_settings(self, initial_tab: str = "") -> None:
        dialog = SettingsDialog(self.store, self, initial_tab=initial_tab)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = self.store.load()
            if self.current_plan is None:
                self.destination_edit.setText(self.config.download_root)
            self.check_connection()

    def closeEvent(self, event: Any) -> None:
        if self.download_running:
            answer = QMessageBox.question(self, "下载尚未完成", "关闭 PanFetch AI 会取消当前下载，确定关闭吗？")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            if self.download_control:
                self.download_control.cancel()
        if self._home_cancellation is not None:
            self._home_cancellation.cancel()
        if self._home_planner is not None:
            self._home_planner.cancel()
        event.accept()


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def _format_plan_timestamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value


def format_time(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M") if timestamp else "-"


def organize_label(value: str) -> str:
    return {"preserve": "保留原目录", "type": "按文件类型", "year": "按年份", "source": "按来源目录"}.get(value, value)


def expand_selected_items(client: Any, selected: list[RemoteItem], progress: Any | None = None) -> list[RemoteItem]:
    report = progress or (lambda _: None)
    by_key: dict[object, RemoteItem] = {
        item.fs_id or item.path: item for item in selected if not item.is_dir
    }
    for directory in (item for item in selected if item.is_dir):
        for remote in client.walk(
            directory.path,
            max_depth=-1,
            limit=0,
            progress=lambda path, count: report({"path": path, "count": count}),
        ):
            if not remote.is_dir:
                by_key[remote.fs_id or remote.path] = remote
    return list(by_key.values())
