from __future__ import annotations

from pathlib import PurePosixPath

from panfetch_ai.core.models import RemoteItem


def download_preview_tree(
    files: list[RemoteItem],
    selected_roots: list[RemoteItem],
    limit: int = 8,
) -> str:
    unique_files = list({item.fs_id or item.path: item for item in files if not item.is_dir}.values())
    groups: list[tuple[str, str, list[RemoteItem]]] = []
    covered: set[object] = set()
    selected_folders = sorted(
        {item.path: item for item in selected_roots if item.is_dir}.values(),
        key=lambda item: (len(PurePosixPath(item.path).parts), item.path.casefold()),
    )
    accepted_folders: list[str] = []
    for folder in selected_folders:
        if any(folder.path == parent or folder.path.startswith(parent.rstrip("/") + "/") for parent in accepted_folders):
            continue
        prefix = folder.path.rstrip("/") + "/"
        matches = [item for item in unique_files if item.path.startswith(prefix)]
        if matches:
            groups.append(("folder", folder.path, matches))
            accepted_folders.append(folder.path)
            covered.update(item.fs_id or item.path for item in matches)

    remaining: dict[str, list[RemoteItem]] = {}
    for item in unique_files:
        if (item.fs_id or item.path) in covered:
            continue
        remaining.setdefault(str(PurePosixPath(item.path).parent), []).append(item)
    for parent, children in sorted(remaining.items(), key=lambda entry: entry[0].casefold()):
        groups.append(("folder" if len(children) > 1 else "file", parent, children))

    visible = groups[: max(1, limit)]
    lines: list[str] = []
    for index, (kind, path, children) in enumerate(visible):
        is_last = index == len(visible) - 1 and len(groups) <= len(visible)
        branch = "└─" if is_last else "├─"
        if kind == "folder":
            lines.append(f"{branch} {path}/  · {len(children)} 个文件 · {_format_size(sum(item.size for item in children))}")
        else:
            lines.append(f"{branch} {children[0].path}  · {_format_size(children[0].size)}")
    if len(groups) > len(visible):
        lines.append(f"└─ 另有 {len(groups) - len(visible)} 组内容")
    return "\n".join(lines)


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"
