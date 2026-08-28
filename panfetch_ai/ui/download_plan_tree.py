from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Iterator

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHeaderView, QStyle, QTreeWidget, QTreeWidgetItem

from panfetch_ai.core.models import RemoteItem


@dataclass(slots=True)
class PlanTreeBranch:
    name: str
    path: str
    folders: dict[str, "PlanTreeBranch"] = field(default_factory=dict)
    files: list[RemoteItem] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.files) + sum(folder.file_count for folder in self.folders.values())

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files) + sum(folder.total_bytes for folder in self.folders.values())


class DownloadPlanTree(QTreeWidget):
    selection_changed = Signal()

    def __init__(self, parent: QTreeWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False
        self.setObjectName("planTree")
        self.setColumnCount(4)
        self.setHeaderLabels(["下载内容", "类型", "文件 / 体积", "网盘路径"])
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.itemChanged.connect(self._item_changed)
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 340)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 90)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 150)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def set_items(self, items: list[RemoteItem]) -> None:
        self._updating = True
        self.clear()
        root = _build_plan_tree(items)
        for branch in sorted(root.folders.values(), key=lambda item: item.name.casefold()):
            self._add_folder(self, branch)
        for remote in sorted(root.files, key=lambda item: item.name.casefold()):
            self._add_file(self, remote)
        self._updating = False
        self.selection_changed.emit()

    def checked_items(self) -> list[RemoteItem]:
        return [
            remote
            for item in self._walk_items()
            if item.checkState(0) == Qt.CheckState.Checked
            and isinstance((remote := item.data(0, Qt.ItemDataRole.UserRole)), RemoteItem)
        ]

    def set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._updating = True
        for item in self._walk_items():
            item.setCheckState(0, state)
        self._updating = False
        self.selection_changed.emit()

    def invert_checks(self) -> None:
        self._updating = True
        for item in self._walk_items():
            if isinstance(item.data(0, Qt.ItemDataRole.UserRole), RemoteItem):
                state = Qt.CheckState.Unchecked if item.checkState(0) == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setCheckState(0, state)
        for index in range(self.topLevelItemCount()):
            self._refresh_folder_state(self.topLevelItem(index))
        self._updating = False
        self.selection_changed.emit()

    def _add_folder(self, parent: QTreeWidget | QTreeWidgetItem, branch: PlanTreeBranch) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent)
        item.setText(0, branch.name)
        item.setText(1, "文件夹")
        item.setText(2, f"{branch.file_count} 个文件 · {_format_size(branch.total_bytes)}")
        item.setText(3, branch.path)
        item.setFont(3, QFont("Cascadia Mono", 9))
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, branch.path)
        for child in sorted(branch.folders.values(), key=lambda value: value.name.casefold()):
            self._add_folder(item, child)
        for remote in sorted(branch.files, key=lambda value: value.name.casefold()):
            self._add_file(item, remote)
        item.setExpanded(False)
        return item

    def _add_file(self, parent: QTreeWidget | QTreeWidgetItem, remote: RemoteItem) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent)
        item.setText(0, remote.name)
        item.setText(1, PurePosixPath(remote.name).suffix.lower() or "文件")
        item.setText(2, _format_size(remote.size))
        item.setText(3, remote.path)
        item.setFont(3, QFont("Cascadia Mono", 9))
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        item.setData(0, Qt.ItemDataRole.UserRole, remote)
        return item

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0:
            return
        self._updating = True
        if item.checkState(0) in {Qt.CheckState.Checked, Qt.CheckState.Unchecked}:
            self._set_descendants(item, item.checkState(0))
        parent = item.parent()
        while parent is not None:
            self._set_parent_state(parent)
            parent = parent.parent()
        self._updating = False
        self.selection_changed.emit()

    def _set_descendants(self, item: QTreeWidgetItem, state: Qt.CheckState) -> None:
        for index in range(item.childCount()):
            child = item.child(index)
            child.setCheckState(0, state)
            self._set_descendants(child, state)

    @staticmethod
    def _set_parent_state(item: QTreeWidgetItem) -> None:
        states = {item.child(index).checkState(0) for index in range(item.childCount())}
        if states == {Qt.CheckState.Checked}:
            item.setCheckState(0, Qt.CheckState.Checked)
        elif states == {Qt.CheckState.Unchecked}:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            item.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def _refresh_folder_state(self, item: QTreeWidgetItem) -> None:
        for index in range(item.childCount()):
            self._refresh_folder_state(item.child(index))
        if item.childCount():
            self._set_parent_state(item)

    def _walk_items(self) -> Iterator[QTreeWidgetItem]:
        def walk(item: QTreeWidgetItem) -> Iterator[QTreeWidgetItem]:
            yield item
            for child_index in range(item.childCount()):
                yield from walk(item.child(child_index))

        for top_index in range(self.topLevelItemCount()):
            yield from walk(self.topLevelItem(top_index))


def _build_plan_tree(items: list[RemoteItem]) -> PlanTreeBranch:
    root = PlanTreeBranch("", "/")
    deduplicated = {item.fs_id or item.path: item for item in items if not item.is_dir}
    for remote in deduplicated.values():
        branch = root
        current_path = ""
        for part in PurePosixPath(remote.path).parent.parts:
            if part == "/":
                continue
            current_path = f"{current_path}/{part}"
            branch = branch.folders.setdefault(part, PlanTreeBranch(part, current_path))
        branch.files.append(remote)
    return root


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"
