from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from panfetch_ai.core.plan_history import PlanHistorySummary


class PlanHistoryPage(QWidget):
    """Dense plan library that opens one download plan at a time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self.setObjectName("planHistoryPage")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        heading_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("下载计划")
        title.setObjectName("planHistoryTitle")
        subtitle = QLabel("按生成时间查看历史计划，选择一项后进入文件夹预览和下载确认。")
        subtitle.setProperty("muted", True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        heading_row.addLayout(title_box, 1)
        self.back_button = QPushButton("返回问答")
        self.back_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
        heading_row.addWidget(self.back_button)
        layout.addLayout(heading_row)

        meta_row = QHBoxLayout()
        self.count_label = QLabel("暂无历史计划")
        self.count_label.setProperty("sectionTitle", True)
        meta_row.addWidget(self.count_label)
        meta_row.addStretch(1)
        self.open_button = QPushButton("查看详情")
        self.open_button.setProperty("primary", True)
        self.open_button.setEnabled(False)
        meta_row.addWidget(self.open_button)
        layout.addLayout(meta_row)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("planHistoryTable")
        self.table.setHorizontalHeaderLabels(["生成时间", "需求", "来源", "文件", "体积", "保存位置"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 155)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(2, 240)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 82)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 100)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(5, 280)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("还没有下载计划。\n在 AI 问答中提出下载要求，生成后会保存在这里。")
        self.empty_label.setObjectName("planHistoryEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setProperty("muted", True)
        layout.addWidget(self.empty_label, 1)
        self._show_empty(True)

    def populate(self, summaries: list[PlanHistorySummary]) -> None:
        previous_record_id = self.selected_record_id()
        self.table.setRowCount(len(summaries))
        selected_row = 0
        for row, summary in enumerate(summaries):
            created = QTableWidgetItem(_format_timestamp(summary.created_at))
            created.setData(Qt.ItemDataRole.UserRole, summary.record_id)
            request = QTableWidgetItem(summary.request)
            request.setToolTip(summary.request)
            sources = QTableWidgetItem(_source_summary(summary.source_paths))
            sources.setToolTip("\n".join(summary.source_paths))
            count = QTableWidgetItem(f"{summary.file_count} 个")
            count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            size = QTableWidgetItem(_format_size(summary.total_bytes))
            size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            destination = QTableWidgetItem(summary.destination)
            destination.setFont(QFont("Cascadia Mono", 9))
            destination.setToolTip(summary.destination)
            for column, item in enumerate((created, request, sources, count, size, destination)):
                self.table.setItem(row, column, item)
            if summary.record_id == previous_record_id:
                selected_row = row
        self.count_label.setText(f"共 {len(summaries)} 个历史计划" if summaries else "暂无历史计划")
        self._show_empty(not summaries)
        if summaries:
            self.table.selectRow(selected_row)
        else:
            self.open_button.setEnabled(False)

    def selected_record_id(self) -> str:
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self.open_button.setText("正在读取…" if loading else "查看详情")
        self.open_button.setEnabled(not loading and bool(self.selected_record_id()))
        self.table.setEnabled(not loading)

    @property
    def is_loading(self) -> bool:
        return self._loading

    def _selection_changed(self) -> None:
        self.open_button.setEnabled(not self._loading and bool(self.selected_record_id()))

    def _show_empty(self, empty: bool) -> None:
        self.table.setVisible(not empty)
        self.empty_label.setVisible(empty)


def _format_timestamp(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value[:16]


def _source_summary(paths: list[str]) -> str:
    if not paths:
        return "-"
    if len(paths) == 1:
        return paths[0]
    return f"{paths[0]} 等 {len(paths)} 个路径"


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"
