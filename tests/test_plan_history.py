from __future__ import annotations

from panfetch_ai.core.models import PlanPreview, RemoteItem, SelectionPlan
from panfetch_ai.core.plan_history import PlanHistoryStore


def test_plan_history_persists_summaries_and_full_preview(tmp_path) -> None:
    store = PlanHistoryStore(tmp_path / "download_plans.db")
    first = PlanPreview(
        SelectionPlan(source_paths=["/课程"], destination=str(tmp_path), reasoning="第一批"),
        [RemoteItem(1, "/课程/讲义.pdf", "讲义.pdf", False, size=120)],
        3,
        {"命中排除扩展名": 3},
    )
    second = PlanPreview(
        SelectionPlan(source_paths=["/代码"], destination=str(tmp_path), reasoning="第二批"),
        [RemoteItem(2, "/代码/demo.zip", "demo.zip", False, size=340)],
        0,
        {},
    )

    first_record = store.save("下载课程讲义", first)
    second_record = store.save("下载示例代码", second)
    summaries = store.summaries()

    assert [item.record_id for item in summaries] == [second_record.summary.record_id, first_record.summary.record_id]
    assert summaries[0].request == "下载示例代码"
    assert summaries[0].file_count == 1
    restored = store.get(first_record.summary.record_id)
    assert restored is not None
    assert restored.preview.plan.source_paths == ["/课程"]
    assert restored.preview.selected[0].path == "/课程/讲义.pdf"
    assert restored.preview.excluded_reasons == {"命中排除扩展名": 3}


def test_plan_history_read_does_not_create_empty_database(tmp_path) -> None:
    path = tmp_path / "download_plans.db"
    store = PlanHistoryStore(path)
    assert store.summaries() == []
    assert store.get("missing") is None
    assert path.exists() is False
