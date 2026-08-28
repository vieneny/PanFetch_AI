from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QListWidgetItem

from panfetch_ai.app import create_application
from panfetch_ai.core.models import PlanPreview, RemoteItem, SelectionPlan
from panfetch_ai.core.operations import build_operation_plan
from panfetch_ai.ui.main_window import MainWindow
from panfetch_ai.ui.settings_dialog import SettingsDialog


OUTPUT = Path(os.getenv("PANFETCH_UI_OUTPUT", Path(__file__).resolve().parents[1] / "artifacts"))


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    os.environ["PANFETCH_SKIP_AUTOCONNECT"] = "1"
    render_history = OUTPUT / "render-download-plans.db"
    render_history.unlink(missing_ok=True)
    os.environ["PANFETCH_PLAN_HISTORY_DB"] = str(render_history)
    app = create_application([])
    window = MainWindow()
    window.load_directory = lambda *_: None
    window._connection_ready(
        (
            {"netdisk_name": "演示账号", "uk": 10001, "vip_type": 2},
            {"total": 2 * 1024**4, "used": 680 * 1024**3, "expire": False},
            b"",
        )
    )
    sample_items = [
        RemoteItem(1, "/示例课程/基础模块", "基础模块", True, modified=1787846400),
        RemoteItem(2, "/示例课程/集合讲义.pdf", "集合讲义.pdf", False, size=2_450_000, modified=1787846400),
        RemoteItem(3, "/示例课程/示例代码.zip", "示例代码.zip", False, size=860_000, modified=1787846400),
    ]
    window._directory_ready(
        (
            "/示例课程",
            sample_items,
        )
    )
    plan = SelectionPlan(
        source_paths=["/示例课程"],
        include_extensions=[".pdf", ".zip"],
        exclude_extensions=[".mp4", ".exe"],
        destination=window.config.download_root,
        organize_by="source",
        reasoning="保留讲义和示例代码，排除视频与安装包。",
    )
    window._plan_ready(
        PlanPreview(plan, sample_items[1:], 5, {"目录": 1, "命中排除扩展名": 4}),
        request="下载课程讲义和示例代码",
    )
    archive_plan = SelectionPlan(
        source_paths=["/示例课程/基础模块"],
        include_extensions=[".pdf"],
        destination=window.config.download_root,
        reasoning="只保留基础模块讲义。",
    )
    window._plan_ready(
        PlanPreview(archive_plan, [sample_items[1]], 2, {"命中排除扩展名": 2}),
        request="整理基础模块 PDF 讲义",
    )
    window.home_conversation.clear()
    window.home_conversation.append_message("user", "帮我找到 Java 集合相关资料，并告诉我在哪。")
    window.home_conversation.append_message(
        "assistant",
        "已在课程资料中定位到集合讲义、示例代码和练习文档。候选结果已发送到网盘工作台。",
    )
    window.home_thinking.setPlainText("正在判断资料范围…\n正在归纳目录名、文件格式和路径样例…")
    window.home_stage.setText("完成 · search")
    window.home_trace.setPlainText("作用域：/\n路由：search\n工具完成：search，返回 12 项")
    window.history_list.clear()
    window.history_list.addItem(QListWidgetItem("查找 Java 集合资料\n2 轮"))
    window.history_list.addItem(QListWidgetItem("下载课程讲义\n1 轮"))
    window.show()

    def capture_main() -> None:
        window.resize(1480, 900)
        window.grab().save(str(OUTPUT / "panfetch-ai-home.png"))
        window.resize(1120, 720)
        QTimer.singleShot(250, capture_narrow_home)

    def capture_narrow_home() -> None:
        window.grab().save(str(OUTPUT / "panfetch-ai-home-narrow.png"))
        window.resize(1480, 900)
        window.home_details_toggle.setChecked(True)
        QTimer.singleShot(250, capture_expanded_home)

    def capture_expanded_home() -> None:
        window.grab().save(str(OUTPUT / "panfetch-ai-home-details.png"))
        window.home_details_toggle.setChecked(False)
        window.switch_page(1)
        window.grab().save(str(OUTPUT / "panfetch-ai-workspace.png"))
        window.grab().save(str(OUTPUT / "panfetch-ai-quick.png"))
        window.open_plan_history()
        window.grab().save(str(OUTPUT / "panfetch-ai-plans.png"))
        window.resize(1120, 720)
        QTimer.singleShot(250, capture_narrow_plans)

    def capture_narrow_plans() -> None:
        window.grab().save(str(OUTPUT / "panfetch-ai-plans-narrow.png"))
        window.resize(1480, 900)
        window.plan_history_page.table.selectRow(1)
        window.open_selected_plan()
        window.grab().save(str(OUTPUT / "panfetch-ai-plan.png"))
        window.resize(1120, 720)
        QTimer.singleShot(250, capture_narrow_plan)

    def capture_narrow_plan() -> None:
        window.grab().save(str(OUTPUT / "panfetch-ai-plan-narrow.png"))
        window.resize(1480, 900)
        window._show_operation_plan(
            build_operation_plan(
                "move",
                {"source": "/示例课程/集合讲义.pdf", "destination": "/学习归档"},
                "界面演示",
            )
        )
        window.grab().save(str(OUTPUT / "panfetch-ai-operation.png"))
        dialog = SettingsDialog(window.store, window)
        window._qa_settings_dialog = dialog
        dialog.show()
        QTimer.singleShot(600, capture_settings)

    def capture_settings() -> None:
        dialog = window._qa_settings_dialog
        dialog.grab().save(str(OUTPUT / "panfetch-ai-settings-baidu.png"))
        dialog.tabs.setCurrentIndex(1)
        QTimer.singleShot(250, capture_llm_settings)

    def capture_llm_settings() -> None:
        dialog = window._qa_settings_dialog
        dialog.grab().save(str(OUTPUT / "panfetch-ai-settings-llm.png"))
        dialog.close()
        window.close()
        app.quit()

    QTimer.singleShot(3500, capture_main)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
