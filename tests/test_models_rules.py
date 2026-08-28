from __future__ import annotations

from panfetch_ai.core.models import RemoteItem, SelectionPlan
from panfetch_ai.core.rules import build_preview, evaluate


def item(path: str, size: int = 1) -> RemoteItem:
    return RemoteItem(abs(hash(path)), path, path.rsplit("/", 1)[-1], False, size=size)


def test_plan_normalizes_paths_extensions_and_modes() -> None:
    plan = SelectionPlan.from_dict(
        {
            "source_paths": ["学习资料"],
            "include_extensions": ["PDF", ".DOCX"],
            "organize_by": "unsupported",
            "match_mode": "all",
        },
        "F:\\downloads",
    )
    assert plan.source_paths == ["/学习资料"]
    assert plan.include_extensions == [".pdf", ".docx"]
    assert plan.organize_by == "preserve"
    assert plan.match_mode == "all"


def test_rule_any_mode_accepts_keyword_or_extension() -> None:
    plan = SelectionPlan(include_keywords=["真题"], include_extensions=[".pdf"], match_mode="any")
    assert evaluate(item("/数学/真题.docx"), plan)[0]
    assert evaluate(item("/数学/讲义.pdf"), plan)[0]
    assert not evaluate(item("/数学/讲义.docx"), plan)[0]


def test_preview_counts_exclusion_reasons() -> None:
    plan = SelectionPlan(include_extensions=[".pdf"], exclude_keywords=["答案"])
    preview = build_preview(plan, [item("/真题.pdf", 10), item("/答案.pdf", 5), item("/说明.txt", 3)])
    assert [entry.path for entry in preview.selected] == ["/真题.pdf"]
    assert preview.total_bytes == 10
    assert preview.excluded_count == 2
    assert preview.excluded_reasons == {"命中排除关键词": 1, "未命中包含条件": 1}
