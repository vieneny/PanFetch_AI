from __future__ import annotations

from typing import Any

import pytest

from panfetch_ai.core.netdisk import BaiduNetdiskClient, normalize_remote_path


class Response:
    ok = True
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload


class Session:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = iter(payloads)
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def get(self, *args: Any, **kwargs: Any) -> Response:
        self.calls.append((args, kwargs))
        return Response(next(self.payloads))


class PostSession:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = iter(payloads)
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def post(self, *args: Any, **kwargs: Any) -> Response:
        self.calls.append((args, kwargs))
        return Response(next(self.payloads))


def test_normalize_remote_path() -> None:
    assert normalize_remote_path("/学习资料/") == "/学习资料"
    assert normalize_remote_path("/学习资料/./Java") == "/学习资料/Java"
    with pytest.raises(ValueError):
        normalize_remote_path("学习资料")
    with pytest.raises(ValueError, match="不能包含"):
        normalize_remote_path("/学习资料/../私密")


def test_list_directory_converts_and_sorts_directories_first() -> None:
    session = Session(
        [
            {
                "errno": 0,
                "has_more": 0,
                "list": [
                    {"fs_id": 1, "path": "/z.txt", "server_filename": "z.txt", "isdir": 0, "size": 2},
                    {"fs_id": 2, "path": "/目录", "server_filename": "目录", "isdir": 1, "size": 0},
                ],
            }
        ]
    )
    items = BaiduNetdiskClient(token="secret", session=session).list_directory("/")
    assert [item.name for item in items] == ["目录", "z.txt"]


def test_account_and_quota_use_official_openapi_endpoints() -> None:
    session = Session(
        [
            {"errno": 0, "netdisk_name": "测试账号", "uk": 42, "vip_type": 2, "avatar_url": "https://example.test/a.png"},
            {"errno": 0, "total": 1000, "used": 250, "free": 100, "expire": False},
        ]
    )
    client = BaiduNetdiskClient(token="secret", session=session)

    assert client.account_info()["vip_type"] == 2
    assert client.quota_info() == {"total": 1000, "used": 250, "free": 100, "expire": False}
    assert session.calls[0][0][0].endswith("/rest/2.0/xpan/nas")
    assert session.calls[0][1]["params"]["method"] == "uinfo"
    assert session.calls[1][0][0].endswith("/api/quota")
    assert session.calls[1][1]["params"]["checkexpire"] == 1
    assert session.calls[1][1]["params"]["checkfree"] == 1


def test_file_manager_move_uses_official_post_payload() -> None:
    session = PostSession([{"errno": 0, "info": [{"errno": 0}]}])
    BaiduNetdiskClient(token="secret", session=session).move("/report.pdf", "/backup")

    url = session.calls[0][0][0]
    kwargs = session.calls[0][1]
    assert url.endswith("/rest/2.0/xpan/file")
    assert kwargs["params"]["method"] == "filemanager"
    assert kwargs["params"]["opera"] == "move"
    assert '"dest":"/backup"' in kwargs["data"]["filelist"]


def test_create_share_resolves_full_disk_paths_to_fsids() -> None:
    class McpClient:
        def __init__(self) -> None:
            self.calls = []

        def create_share(self, fs_ids, period):
            self.calls.append((fs_ids, period))
            return {"link": "https://pan.baidu.com/s/example", "pwd": "a1b2"}

    session = Session(
        [
            {
                "errno": 0,
                "has_more": 0,
                "list": [
                    {"fs_id": 101, "path": "/课程/Java", "server_filename": "Java", "isdir": 1},
                    {"fs_id": 102, "path": "/课程/note.pdf", "server_filename": "note.pdf", "isdir": 0},
                ],
            }
        ]
    )
    mcp = McpClient()
    client = BaiduNetdiskClient(token="secret", session=session, mcp_client=mcp)

    result = client.create_share(["/课程/Java", "/课程/note.pdf"], 30)

    assert mcp.calls == [([101, 102], 30)]
    assert result["pwd"] == "a1b2"


def test_upload_file_uses_precreate_chunk_and_create(tmp_path) -> None:
    local = tmp_path / "note.txt"
    local.write_text("hello", encoding="utf-8")
    session = PostSession(
        [
            {"errno": 0, "uploadid": "upload-1"},
            {"errno": 0, "md5": "chunk-md5"},
            {"errno": 0, "fs_id": 99},
        ]
    )

    result = BaiduNetdiskClient(token="secret", session=session).upload_file(local, "/资料/note.txt")

    assert result == {"path": "/资料/note.txt", "size": 5, "fs_id": 99}
    assert session.calls[0][1]["params"]["method"] == "precreate"
    assert session.calls[1][1]["params"]["method"] == "upload"
    assert session.calls[2][1]["params"]["method"] == "create"
