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


def test_custom_headers_reject_embedded_api_keys() -> None:
    with pytest.raises(ValueError):
        parse_headers('{"x-api-key": "must-not-be-plain-text"}')
