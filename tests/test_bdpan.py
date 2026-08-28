from __future__ import annotations

from panfetch_ai.core.bdpan import BdpanBackend


def test_missing_bdpan_is_optional_and_does_not_affect_full_disk_share(monkeypatch) -> None:
    monkeypatch.setattr("panfetch_ai.core.bdpan.shutil.which", lambda _name: None)

    status = BdpanBackend().status()

    assert status.available is False
    assert "仅分享链接转存和下载" in status.detail
    assert "不影响全盘分享" in status.detail
