from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from panfetch_ai.core.config import PROJECT_ROOT
from panfetch_ai.core.models import RemoteItem


DEFAULT_DB = PROJECT_ROOT / ".panfetch-ai" / "catalog.db"
UNSCOPED_ACCOUNT = "__unscoped__"


class Catalog:
    def __init__(self, path: Path = DEFAULT_DB, account_id: str = "") -> None:
        self.path = path
        self.account_id = _normalize_account_id(account_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def set_account(self, account_id: str) -> None:
        self.account_id = _normalize_account_id(account_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(remote_items)").fetchall()
            }
            if columns and "account_id" not in columns:
                connection.execute("DROP TABLE remote_items")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS remote_items (
                    account_id TEXT NOT NULL,
                    fs_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    is_dir INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    modified INTEGER NOT NULL,
                    md5 TEXT,
                    indexed_at INTEGER NOT NULL,
                    PRIMARY KEY(account_id, fs_id),
                    UNIQUE(account_id, path)
                );
                CREATE INDEX IF NOT EXISTS idx_remote_items_path ON remote_items(account_id, path);
                CREATE INDEX IF NOT EXISTS idx_remote_items_name ON remote_items(account_id, name);
                """
            )

    def upsert(self, items: list[RemoteItem]) -> int:
        now = int(time.time())
        account_id = self.account_id
        rows = [
            (account_id, item.fs_id, item.path, item.name, int(item.is_dir), item.size, item.modified, item.md5, now)
            for item in items
            if item.fs_id
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO remote_items(
                    account_id, fs_id, path, name, is_dir, size, modified, md5, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def search(self, keyword: str, limit: int = 200) -> list[RemoteItem]:
        pattern = f"%{keyword.strip()}%"
        account_id = self.account_id
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM remote_items
                WHERE account_id = ? AND (name LIKE ? OR path LIKE ?)
                ORDER BY is_dir DESC, name LIMIT ?
                """,
                (account_id, pattern, pattern, max(1, limit)),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def children(self, parent_path: str) -> list[RemoteItem]:
        prefix = parent_path.rstrip("/")
        prefix = "" if prefix == "/" else prefix
        depth = prefix.count("/") + 1
        account_id = self.account_id
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM remote_items
                WHERE account_id = ? AND path LIKE ? AND path NOT LIKE ?
                  AND (LENGTH(path) - LENGTH(REPLACE(path, '/', ''))) = ?
                ORDER BY is_dir DESC, name
                """,
                (account_id, f"{prefix}/%", f"{prefix}/%/%", depth),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def stats(self) -> dict[str, int]:
        account_id = self.account_id
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN is_dir=1 THEN 1 ELSE 0 END) AS dirs,
                       SUM(size) AS bytes
                FROM remote_items WHERE account_id = ?
                """,
                (account_id,),
            ).fetchone()
        return {"total": int(row["total"] or 0), "dirs": int(row["dirs"] or 0), "bytes": int(row["bytes"] or 0)}


def _normalize_account_id(account_id: str) -> str:
    return account_id.strip() or UNSCOPED_ACCOUNT


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
