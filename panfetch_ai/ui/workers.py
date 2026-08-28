from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(object)
    finished = Signal()


class TaskRunner(QRunnable):
    def __init__(self, function: Callable[[Callable[[Any], None]], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        def report(value: Any) -> None:
            self._emit_safely(self.signals.progress, value)

        try:
            result = self.function(report)
        except Exception as exc:
            detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self._emit_safely(self.signals.error, detail)
        else:
            self._emit_safely(self.signals.result, result)
        finally:
            self._emit_safely(self.signals.finished)

    @staticmethod
    def _emit_safely(signal: Any, *args: Any) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            # The window may be gone while a network task is winding down.
            return
