from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from panfetch_ai.core.config import PROJECT_ROOT


LOGGER_NAME = "panfetch_ai"


def configure_logging() -> Path:
    folder = PROJECT_ROOT / "logs" / datetime.now().strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    log_file = folder / "panfetch-ai.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_file for handler in logger.handlers):
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    return log_file


def log_info(message: str) -> None:
    logging.getLogger(LOGGER_NAME).info(redact(message))


def install_exception_hook() -> None:
    def handle(exc_type: type[BaseException], exc: BaseException, traceback: TracebackType | None) -> None:
        logger = logging.getLogger(LOGGER_NAME)
        logger.error("Unhandled exception: %s", redact(str(exc)), exc_info=(exc_type, exc, traceback))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(None, "PanFetch AI 运行错误", "程序遇到未处理错误，请查看 logs 目录中的运行日志。")
                return
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, traceback)

    sys.excepthook = handle


def redact(value: str) -> str:
    text = value
    patterns = [
        (r"(?i)(access_token=)[^&\s]+", r"\1<redacted>"),
        (r"(?i)(authorization[:=]\s*bearer\s+)[A-Za-z0-9._-]+", r"\1<redacted>"),
        (r"(?i)(x-api-key|api-key)([:=]\s*)[^,;\s]+", r"\1\2<redacted>"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text
