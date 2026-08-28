from __future__ import annotations

from panfetch_ai.core.models import RemoteItem
from panfetch_ai.core.plan_preview import download_preview_tree
from panfetch_ai.ui.main_window import expand_selected_items


class Client:
    def walk(self, path, max_depth=-1, limit=0, progress=None):
        if progress:
            progress(path, 3)
        return [
            RemoteItem(10, f"{path}/子目录", "子目录", True),
            RemoteItem(11, f"{path}/讲义.pdf", "讲义.pdf", False, size=100),
            RemoteItem(12, f"{path}/代码.zip", "代码.zip", False, size=200),
        ]


def test_selected_folder_expands_to_files_and_deduplicates() -> None:
    folder = RemoteItem(1, "/课程", "课程", True)
    duplicate = RemoteItem(11, "/课程/讲义.pdf", "讲义.pdf", False, size=100)
    progress = []
    files = expand_selected_items(Client(), [folder, duplicate], progress.append)
    assert {item.fs_id for item in files} == {11, 12}
    assert progress == [{"path": "/课程", "count": 3}]


def test_download_preview_groups_sibling_files_under_parent_folder() -> None:
    files = [
        RemoteItem(1, "/课程/模块一/讲义.pdf", "讲义.pdf", False, size=100),
        RemoteItem(2, "/课程/模块一/代码.zip", "代码.zip", False, size=200),
        RemoteItem(3, "/课程/说明.txt", "说明.txt", False, size=30),
    ]
    preview = download_preview_tree(files, files)
    assert "/课程/模块一/  · 2 个文件 · 300 B" in preview
    assert "/课程/说明.txt  · 30 B" in preview
    assert "讲义.pdf" not in preview


def test_download_preview_prefers_explicit_selected_folder() -> None:
    folder = RemoteItem(10, "/课程", "课程", True)
    files = [
        RemoteItem(1, "/课程/模块一/讲义.pdf", "讲义.pdf", False, size=100),
        RemoteItem(2, "/课程/模块二/代码.zip", "代码.zip", False, size=200),
    ]
    preview = download_preview_tree(files, [folder])
    assert preview == "└─ /课程/  · 2 个文件 · 300 B"
