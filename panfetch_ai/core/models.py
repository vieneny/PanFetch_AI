from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any


@dataclass(slots=True)
class RemoteItem:
    fs_id: int
    path: str
    name: str
    is_dir: bool
    size: int = 0
    modified: int = 0
    md5: str | None = None
    category: int = 0

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "RemoteItem":
        path = str(payload.get("path") or "")
        return cls(
            fs_id=int(payload.get("fs_id", payload.get("fsid", 0)) or 0),
            path=path,
            name=str(payload.get("server_filename") or payload.get("filename") or PurePosixPath(path).name),
            is_dir=bool(payload.get("isdir")),
            size=int(payload.get("size") or 0),
            modified=int(payload.get("server_mtime") or payload.get("local_mtime") or 0),
            md5=str(payload["md5"]) if payload.get("md5") else None,
            category=int(payload.get("category") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SelectionPlan:
    source_paths: list[str] = field(default_factory=lambda: ["/"])
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    include_extensions: list[str] = field(default_factory=list)
    exclude_extensions: list[str] = field(default_factory=list)
    destination: str = ""
    organize_by: str = "preserve"
    match_mode: str = "any"
    reasoning: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any], default_destination: str = "") -> "SelectionPlan":
        def strings(name: str) -> list[str]:
            value = payload.get(name) or []
            if isinstance(value, str):
                value = [value]
            return [str(item).strip() for item in value if str(item).strip()]

        source_paths = [path if path.startswith("/") else f"/{path}" for path in strings("source_paths")]
        organize_by = str(payload.get("organize_by") or "preserve").strip().lower()
        if organize_by not in {"preserve", "type", "year", "source"}:
            organize_by = "preserve"
        match_mode = str(payload.get("match_mode") or "any").strip().lower()
        if match_mode not in {"any", "all"}:
            match_mode = "any"
        return cls(
            source_paths=source_paths or ["/"],
            include_keywords=strings("include_keywords"),
            exclude_keywords=strings("exclude_keywords"),
            include_extensions=_normalize_extensions(strings("include_extensions")),
            exclude_extensions=_normalize_extensions(strings("exclude_extensions")),
            destination=str(payload.get("destination") or default_destination).strip(),
            organize_by=organize_by,
            match_mode=match_mode,
            reasoning=str(payload.get("reasoning") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanPreview:
    plan: SelectionPlan
    selected: list[RemoteItem]
    excluded_count: int
    excluded_reasons: dict[str, int]

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.selected)


@dataclass(slots=True)
class OperationPlan:
    action: str
    title: str
    summary: str
    arguments: dict[str, Any] = field(default_factory=dict)
    backend: str = "openapi"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OperationResult:
    action: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DownloadResult:
    fs_id: int
    remote_path: str
    local_path: str
    status: str
    size: int = 0
    sha256: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_extensions(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        lowered = value.casefold()
        if lowered in {"*", "所有", "all"}:
            return []
        normalized.append(lowered if lowered.startswith(".") else f".{lowered}")
    return normalized
