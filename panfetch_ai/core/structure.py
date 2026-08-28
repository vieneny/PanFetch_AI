from __future__ import annotations

import csv
import io
import re
from pathlib import PurePosixPath

from panfetch_ai.core.models import RemoteItem


def chapter_lines(root: str, items: list[RemoteItem]) -> list[str]:
    directories = sorted((item for item in items if item.is_dir), key=lambda item: natural_key(item.name))
    lines = [f"章节结构：{root}", ""]
    if not directories:
        return lines + ["当前层级没有子目录。"]
    for item in directories:
        prefix = _chapter_prefix(item.name)
        label = prefix or "--"
        lines.append(f"{label}  {item.name}")
    return lines


def tree_text(root: str, items: list[RemoteItem], limit: int = 2000) -> str:
    normalized = root.rstrip("/") or "/"
    lines = [normalized]
    for item in items[:limit]:
        relative = item.path[len(normalized):].lstrip("/") if normalized != "/" else item.path.lstrip("/")
        parts = PurePosixPath(relative).parts
        marker = "[目录]" if item.is_dir else "[文件]"
        suffix = "/" if item.is_dir else ""
        lines.append(f"{'  ' * len(parts)}{marker} {item.name}{suffix}")
    if len(items) > limit:
        lines.append(f"... 其余 {len(items) - limit} 项未显示")
    return "\n".join(lines)


def items_to_csv(items: list[RemoteItem]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["type", "name", "path", "size", "modified", "fs_id", "md5"])
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                "type": "directory" if item.is_dir else "file",
                "name": item.name,
                "path": item.path,
                "size": item.size,
                "modified": item.modified,
                "fs_id": item.fs_id,
                "md5": item.md5 or "",
            }
        )
    return buffer.getvalue()


def natural_key(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value))


def _chapter_prefix(value: str) -> str:
    match = re.match(r"\s*(?:第\s*)?([0-9]{1,3})(?:\s*[章节课、._-]|\s+)", value)
    return f"{int(match.group(1)):02d}" if match else ""
