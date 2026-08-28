from __future__ import annotations

import os
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from panfetch_ai.ui.main_window import MainWindow
from panfetch_ai.ui.styles import APP_STYLE
from panfetch_ai.logging_setup import configure_logging, install_exception_hook, log_info


def create_application(argv: list[str] | None = None) -> QApplication:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QCoreApplication.setOrganizationName("PanFetch AI")
    QCoreApplication.setApplicationName("PanFetch AI")
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationDisplayName("PanFetch AI")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(APP_STYLE)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    return app


def main() -> int:
    log_file = configure_logging()
    install_exception_hook()
    log_info(f"PanFetch AI starting; log={log_file}")
    app = create_application()
    window = MainWindow()
    window.show()
    app.aboutToQuit.connect(lambda: log_info("PanFetch AI stopped"))
    return app.exec()
