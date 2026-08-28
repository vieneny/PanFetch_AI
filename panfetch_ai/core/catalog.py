from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from panfetch_ai.core.config import PROJECT_ROOT
from panfetch_ai.core.models import RemoteItem


DEFAULT_DB = PROJECT_ROOT / ".panfetch-ai" / "catalog.db"


class Catalog:
    def __init__(self, path: Path = DEFAULT_DB) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS remote_items (
                    fs_id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    is_dir INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    modified INTEGER NOT NULL,
                    md5 TEXT,
                    indexed_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_remote_items_path ON remote_items(path);
                CREATE INDEX IF NOT EXISTS idx_remote_items_name ON remote_items(name);
                """
            )

    def upsert(self, items: list[RemoteItem]) -> int:
        now = int(time.time())
        rows = [
            (item.fs_id, item.path, item.name, int(item.is_dir), item.size, item.modified, item.md5, now)
            for item in items
            if item.fs_id
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO remote_items(fs_id, path, name, is_dir, size, modified, md5, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fs_id) DO UPDATE SET
                    path=excluded.path, name=excluded.name, is_dir=excluded.is_dir,
                    size=excluded.size, modified=excluded.modified, md5=excluded.md5,
                    indexed_at=excluded.indexed_at
                """,
                rows,
            )
        return len(rows)

    def search(self, keyword: str, limit: int = 200) -> list[RemoteItem]:
        pattern = f"%{keyword.strip()}%"
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM remote_items WHERE name LIKE ? OR path LIKE ? ORDER BY is_dir DESC, name LIMIT ?",
                (pattern, pattern, max(1, limit)),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def children(self, parent_path: str) -> list[RemoteItem]:
        prefix = parent_path.rstrip("/")
        prefix = "" if prefix == "/" else prefix
        depth = prefix.count("/") + 1
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM remote_items
                WHERE path LIKE ? AND path NOT LIKE ? AND (LENGTH(path) - LENGTH(REPLACE(path, '/', ''))) = ?
                ORDER BY is_dir DESC, name
                """,
                (f"{prefix}/%", f"{prefix}/%/%", depth),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def stats(self) -> dict[str, int]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total, SUM(CASE WHEN is_dir=1 THEN 1 ELSE 0 END) AS dirs, SUM(size) AS bytes FROM remote_items"
            ).fetchone()
        return {"total": int(row["total"] or 0), "dirs": int(row["dirs"] or 0), "bytes": int(row["bytes"] or 0)}


def _row_to_item(row: sqlite3.Row) -> RemoteItem:
    return RemoteItem(
        fs_id=int(row["fs_id"]),
        path=str(row["path"]),
        name=str(row["name"]),
        is_dir=bool(row["is_dir"]),
        size=int(row["size"]),
        modified=int(row["modified"]),
        md5=str(row["md5"]) if row["md5"] else None,
    )
