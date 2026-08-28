from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from panfetch_ai.core.config import PROJECT_ROOT
from panfetch_ai.core.models import PlanPreview, RemoteItem, SelectionPlan


DEFAULT_PLAN_HISTORY_DB = PROJECT_ROOT / ".panfetch-ai" / "download_plans.db"


@dataclass(frozen=True, slots=True)
class PlanHistorySummary:
    record_id: str
    created_at: str
    request: str
    source_paths: list[str]
    file_count: int
    total_bytes: int
    destination: str


@dataclass(frozen=True, slots=True)
class PlanHistoryRecord:
    summary: PlanHistorySummary
    preview: PlanPreview


class PlanHistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_PLAN_HISTORY_DB

    def save(self, request: str, preview: PlanPreview) -> PlanHistoryRecord:
        self._initialize()
        record_id = uuid.uuid4().hex
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        normalized_request = request.strip() or preview.plan.reasoning or "下载计划"
        payload = {
            "plan": preview.plan.to_dict(),
            "selected": [item.to_dict() for item in preview.selected],
            "excluded_count": preview.excluded_count,
            "excluded_reasons": preview.excluded_reasons,
        }
        summary = PlanHistorySummary(
            record_id=record_id,
            created_at=created_at,
            request=normalized_request,
            source_paths=list(preview.plan.source_paths),
            file_count=len(preview.selected),
            total_bytes=preview.total_bytes,
            destination=preview.plan.destination,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO download_plans(
                    record_id, created_at, request, source_paths, file_count,
                    total_bytes, destination, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.record_id,
                    summary.created_at,
                    summary.request,
                    json.dumps(summary.source_paths, ensure_ascii=False, separators=(",", ":")),
                    summary.file_count,
                    summary.total_bytes,
                    summary.destination,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )
        return PlanHistoryRecord(summary, preview)

    def summaries(self, limit: int = 500) -> list[PlanHistorySummary]:
        if not self.path.is_file():
            return []
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT record_id, created_at, request, source_paths,
                           file_count, total_bytes, destination
                    FROM download_plans
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT ?
                    """,
                    (max(1, min(limit, 2000)),),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [self._summary_from_row(row) for row in rows]

    def get(self, record_id: str) -> PlanHistoryRecord | None:
        if not record_id or not self.path.is_file():
            return None
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT record_id, created_at, request, source_paths,
                           file_count, total_bytes, destination, payload
                    FROM download_plans
                    WHERE record_id = ?
                    """,
                    (record_id,),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        try:
            payload: dict[str, Any] = json.loads(str(row["payload"]))
            plan = SelectionPlan.from_dict(dict(payload.get("plan") or {}))
            selected = [RemoteItem(**dict(item)) for item in payload.get("selected") or []]
            excluded_reasons = {
                str(key): int(value) for key, value in dict(payload.get("excluded_reasons") or {}).items()
            }
            preview = PlanPreview(
                plan=plan,
                selected=selected,
                excluded_count=int(payload.get("excluded_count") or 0),
                excluded_reasons=excluded_reasons,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return PlanHistoryRecord(self._summary_from_row(row), preview)

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS download_plans (
                    record_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    request TEXT NOT NULL,
                    source_paths TEXT NOT NULL,
                    file_count INTEGER NOT NULL,
                    total_bytes INTEGER NOT NULL,
                    destination TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_download_plans_created ON download_plans(created_at DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _summary_from_row(row: sqlite3.Row) -> PlanHistorySummary:
        try:
            source_paths = [str(path) for path in json.loads(str(row["source_paths"]))]
        except (TypeError, ValueError, json.JSONDecodeError):
            source_paths = []
        return PlanHistorySummary(
            record_id=str(row["record_id"]),
            created_at=str(row["created_at"]),
            request=str(row["request"]),
            source_paths=source_paths,
            file_count=int(row["file_count"]),
            total_bytes=int(row["total_bytes"]),
            destination=str(row["destination"]),
        )
