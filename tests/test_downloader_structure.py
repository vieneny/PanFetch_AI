from __future__ import annotations

from pathlib import Path

from panfetch_ai.core.downloader import destination_for, safe_component
from panfetch_ai.core.models import RemoteItem, SelectionPlan
from panfetch_ai.core.structure import chapter_lines, items_to_csv


def remote(path: str, is_dir: bool = False) -> RemoteItem:
    return RemoteItem(abs(hash(path)), path, path.rsplit("/", 1)[-1], is_dir, size=10)


def test_destination_preserves_relative_source_hierarchy(tmp_path: Path) -> None:
    plan = SelectionPlan(source_paths=["/学习资料"], destination=str(tmp_path), organize_by="preserve")
    result = destination_for(remote("/学习资料/课程/讲义.pdf"), plan, tmp_path)
    assert result == (tmp_path / "课程" / "讲义.pdf").resolve()


def test_destination_can_organize_by_type(tmp_path: Path) -> None:
    plan = SelectionPlan(source_paths=["/"], destination=str(tmp_path), organize_by="type")
    assert destination_for(remote("/资料/App.java"), plan, tmp_path) == (tmp_path / "代码" / "App.java").resolve()


def test_windows_reserved_names_are_sanitized() -> None:
    assert safe_component("CON.txt") == "_CON.txt"
    assert safe_component("a?.pdf") == "a_.pdf"


def test_chapters_and_csv() -> None:
    items = [remote("/课/10-进阶", True), remote("/课/02-基础", True), remote("/课/readme.txt")]
    lines = chapter_lines("/课", items)
    assert lines[-2:] == ["02  02-基础", "10  10-进阶"]
    csv_text = items_to_csv(items)
    assert "/课/readme.txt" in csv_text
