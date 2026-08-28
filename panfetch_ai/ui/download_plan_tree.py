from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHeaderView, QStyle, QTreeWidget, QTreeWidgetItem

from panfetch_ai.core.models import RemoteItem


REMOTE_ROLE = Qt.ItemDataRole.UserRole
BRANCH_ROLE = Qt.ItemDataRole.UserRole + 1
PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 2


@dataclass(slots=True)
class PlanTreeBranch:
    name: str
    path: str
    folders: dict[str, "PlanTreeBranch"] = field(default_factory=dict)
    files: list[RemoteItem] = field(default_factory=list)
    file_keys: list[str] = field(default_factory=list)
    total_bytes: int = 0

    @property
    def file_count(self) -> int:
        return len(self.file_keys)


class DownloadPlanTree(QTreeWidget):
    selection_changed = Signal()

    def __init__(self, parent: QTreeWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False
        self._items_by_key: dict[str, RemoteItem] = {}
        self._ordered_keys: list[str] = []
        self._selected_keys: set[str] = set()
        self.setObjectName("planTree")
        self.setColumnCount(4)
        self.setHeaderLabels(["下载内容", "类型", "文件 / 体积", "网盘路径"])
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.itemChanged.connect(self._item_changed)
        self.itemExpanded.connect(self._populate_folder)
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
        root, self._items_by_key, self._ordered_keys = _build_plan_tree(items)
        self._selected_keys = set(self._ordered_keys)
        for branch in sorted(root.folders.values(), key=lambda item: item.name.casefold()):
            self._add_folder(self, branch)
        for remote in sorted(root.files, key=lambda item: item.name.casefold()):
            self._add_file(self, remote)
        self._updating = False
        self.selection_changed.emit()

    def clear(self) -> None:
        super().clear()
        self._items_by_key = {}
        self._ordered_keys = []
        self._selected_keys = set()

    def checked_items(self) -> list[RemoteItem]:
        return [self._items_by_key[key] for key in self._ordered_keys if key in self._selected_keys]

    def set_all_checked(self, checked: bool) -> None:
        self._selected_keys = set(self._ordered_keys) if checked else set()
        self._refresh_visible_states()
        self.selection_changed.emit()

    def invert_checks(self) -> None:
        self._selected_keys = set(self._ordered_keys).difference(self._selected_keys)
        self._refresh_visible_states()
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
        item.setData(0, BRANCH_ROLE, branch)
        item.setCheckState(0, self._branch_state(branch))
        if branch.folders or branch.files:
            placeholder = QTreeWidgetItem(item)
            placeholder.setData(0, PLACEHOLDER_ROLE, True)
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
        item.setData(0, REMOTE_ROLE, remote)
        state = Qt.CheckState.Checked if _item_key(remote) in self._selected_keys else Qt.CheckState.Unchecked
        item.setCheckState(0, state)
        return item

    def _populate_folder(self, item: QTreeWidgetItem) -> None:
        branch = item.data(0, BRANCH_ROLE)
        if not isinstance(branch, PlanTreeBranch) or not self._has_placeholder(item):
            return
        self._updating = True
        item.takeChildren()
        for child in sorted(branch.folders.values(), key=lambda value: value.name.casefold()):
            self._add_folder(item, child)
        for remote in sorted(branch.files, key=lambda value: value.name.casefold()):
            self._add_file(item, remote)
        self._updating = False

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0 or item.data(0, PLACEHOLDER_ROLE):
            return
        state = item.checkState(0)
        if state not in {Qt.CheckState.Checked, Qt.CheckState.Unchecked}:
            return
        checked = state == Qt.CheckState.Checked
        branch = item.data(0, BRANCH_ROLE)
        remote = item.data(0, REMOTE_ROLE)
        if isinstance(branch, PlanTreeBranch):
            keys = branch.file_keys
        elif isinstance(remote, RemoteItem):
            keys = [_item_key(remote)]
        else:
            return
        if checked:
            self._selected_keys.update(keys)
        else:
            self._selected_keys.difference_update(keys)
        self._refresh_visible_states()
        self.selection_changed.emit()

    def _refresh_visible_states(self) -> None:
        self._updating = True

        def refresh(item: QTreeWidgetItem) -> None:
            branch = item.data(0, BRANCH_ROLE)
            remote = item.data(0, REMOTE_ROLE)
            if isinstance(branch, PlanTreeBranch):
                item.setCheckState(0, self._branch_state(branch))
            elif isinstance(remote, RemoteItem):
                state = Qt.CheckState.Checked if _item_key(remote) in self._selected_keys else Qt.CheckState.Unchecked
                item.setCheckState(0, state)
            for index in range(item.childCount()):
                child = item.child(index)
                if not child.data(0, PLACEHOLDER_ROLE):
                    refresh(child)

        for index in range(self.topLevelItemCount()):
            refresh(self.topLevelItem(index))
        self._updating = False

    def _branch_state(self, branch: PlanTreeBranch) -> Qt.CheckState:
        selected_count = sum(key in self._selected_keys for key in branch.file_keys)
        if not selected_count:
            return Qt.CheckState.Unchecked
        if selected_count == branch.file_count:
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked

    @staticmethod
    def _has_placeholder(item: QTreeWidgetItem) -> bool:
        return item.childCount() == 1 and bool(item.child(0).data(0, PLACEHOLDER_ROLE))


def _build_plan_tree(items: list[RemoteItem]) -> tuple[PlanTreeBranch, dict[str, RemoteItem], list[str]]:
    root = PlanTreeBranch("", "/")
    items_by_key = {_item_key(remote): remote for remote in items if not remote.is_dir}
    ordered_keys = list(items_by_key)
    for key, remote in items_by_key.items():
        branch = root
        branch.file_keys.append(key)
        branch.total_bytes += remote.size
        current_path = ""
        for part in PurePosixPath(remote.path).parent.parts:
            if part == "/":
                continue
            current_path = f"{current_path}/{part}"
            branch = branch.folders.setdefault(part, PlanTreeBranch(part, current_path))
            branch.file_keys.append(key)
            branch.total_bytes += remote.size
        branch.files.append(remote)
    return root, items_by_key, ordered_keys


def _item_key(item: RemoteItem) -> str:
    return f"id:{item.fs_id}" if item.fs_id else f"path:{item.path}"


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"
