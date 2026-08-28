from __future__ import annotations

import json
from pathlib import Path

from panfetch_ai.core.catalog import Catalog
import pytest

from panfetch_ai.core.config import AppConfig, ConfigStore, LLMConfig, parse_headers
from panfetch_ai.core.models import RemoteItem


def test_config_saves_no_api_keys(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    store = ConfigStore(settings, tmp_path / "secrets")
    config = AppConfig(
        download_root=str(tmp_path / "downloads"),
        concurrency=7,
        llm=LLMConfig(base_url="https://example.test/v1", model="model"),
    )
    store.save(config)
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["concurrency"] == 7
    assert "api_key" not in payload
    assert "api_key" not in payload["llm"]
    assert "token" not in payload


def test_delete_baidu_token_removes_only_baidu_credential(tmp_path: Path, monkeypatch) -> None:
    store = ConfigStore(tmp_path / "settings.json", tmp_path / "secrets")
    store.baidu_token_file.parent.mkdir(parents=True)
    store.baidu_token_file.write_bytes(b"encrypted-baidu")
    store.llm_key_file.write_bytes(b"encrypted-llm")
    monkeypatch.setenv("BAIDU_NETDISK_ACCESS_TOKEN", "temporary")

    assert store.delete_baidu_token() is True
    assert not store.baidu_token_file.exists()
    assert store.llm_key_file.read_bytes() == b"encrypted-llm"
    assert "BAIDU_NETDISK_ACCESS_TOKEN" not in __import__("os").environ


def test_catalog_indexes_and_searches(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path / "catalog.db")
    catalog.upsert(
        [
            RemoteItem(1, "/学习资料/课程", "课程", True),
            RemoteItem(2, "/学习资料/课程/讲义.pdf", "讲义.pdf", False, size=42),
        ]
    )
    results = catalog.search("讲义")
    assert [item.path for item in results] == ["/学习资料/课程/讲义.pdf"]
    assert catalog.stats() == {"total": 2, "dirs": 1, "bytes": 42}


def test_catalog_isolates_same_paths_and_file_ids_by_account(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path / "catalog.db", "uk:first")
    catalog.upsert([RemoteItem(1, "/课程/讲义.pdf", "讲义.pdf", False, size=10)])

    catalog.set_account("uk:second")
    catalog.upsert([RemoteItem(1, "/课程/讲义.pdf", "讲义.pdf", False, size=20)])
    assert catalog.stats() == {"total": 1, "dirs": 0, "bytes": 20}

    catalog.set_account("uk:first")
    assert catalog.stats() == {"total": 1, "dirs": 0, "bytes": 10}


def test_catalog_replaces_stale_path_or_file_id_within_one_account(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path / "catalog.db", "uk:one")
    catalog.upsert([RemoteItem(1, "/旧位置.pdf", "旧位置.pdf", False, size=10)])
    catalog.upsert([RemoteItem(2, "/旧位置.pdf", "旧位置.pdf", False, size=20)])
    catalog.upsert([RemoteItem(2, "/新位置.pdf", "新位置.pdf", False, size=30)])

    assert catalog.search("旧位置") == []
    assert [(item.fs_id, item.path, item.size) for item in catalog.search("新位置")] == [
        (2, "/新位置.pdf", 30)
    ]


def test_catalog_migrates_legacy_single_account_schema(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "catalog.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE remote_items (
                fs_id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
                is_dir INTEGER NOT NULL, size INTEGER NOT NULL, modified INTEGER NOT NULL,
                md5 TEXT, indexed_at INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO remote_items VALUES (1, '/旧账号.pdf', '旧账号.pdf', 0, 1, 0, NULL, 0)"
        )

    catalog = Catalog(path, "uk:new")
    assert catalog.stats() == {"total": 0, "dirs": 0, "bytes": 0}
    catalog.upsert([RemoteItem(2, "/新账号.pdf", "新账号.pdf", False, size=2)])
    assert [item.path for item in catalog.search("新账号")] == ["/新账号.pdf"]


def test_custom_headers_reject_embedded_api_keys() -> None:
    with pytest.raises(ValueError):
        parse_headers('{"x-api-key": "must-not-be-plain-text"}')
