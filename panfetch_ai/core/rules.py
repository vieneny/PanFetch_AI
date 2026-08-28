from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath

from panfetch_ai.core.models import PlanPreview, RemoteItem, SelectionPlan


DEFAULT_VIDEO_EXTENSIONS = {
    ".3gp", ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg",
    ".mts", ".rm", ".rmvb", ".ts", ".vob", ".webm", ".wmv",
}
DEFAULT_INSTALLER_EXTENSIONS = {
    ".apk", ".appx", ".cab", ".deb", ".dmg", ".exe", ".iso", ".msi", ".msix", ".pkg",
    ".rpm", ".vdi", ".vhd", ".vhdx", ".vmdk",
}


def evaluate(item: RemoteItem, plan: SelectionPlan) -> tuple[bool, str]:
    if item.is_dir:
        return False, "目录"
    path = item.path.casefold()
    suffix = PurePosixPath(item.path).suffix.casefold()
    if any(keyword.casefold() in path for keyword in plan.exclude_keywords):
        return False, "命中排除关键词"
    if suffix in plan.exclude_extensions:
        return False, "命中排除扩展名"

    checks: list[bool] = []
    if plan.include_keywords:
        checks.append(any(keyword.casefold() in path for keyword in plan.include_keywords))
    if plan.include_extensions:
        checks.append(suffix in plan.include_extensions)
    if checks:
        matched = all(checks) if plan.match_mode == "all" else any(checks)
        if not matched:
            return False, "未命中包含条件"
    return True, "已选择"


def build_preview(plan: SelectionPlan, items: list[RemoteItem]) -> PlanPreview:
    selected: list[RemoteItem] = []
    reasons: Counter[str] = Counter()
    for item in items:
        accepted, reason = evaluate(item, plan)
        if accepted:
            selected.append(item)
        else:
            reasons[reason] += 1
    return PlanPreview(plan=plan, selected=selected, excluded_count=sum(reasons.values()), excluded_reasons=dict(reasons))


def safe_default_exclusions() -> list[str]:
    return sorted(DEFAULT_VIDEO_EXTENSIONS | DEFAULT_INSTALLER_EXTENSIONS)
