"""Run blocking service calls off the GUI thread and deliver results on the GUI thread.

Signals are emitted from the worker thread and received by a ``_Bridge`` QObject
that lives in the GUI thread (queued connection), so callbacks may safely touch
widgets. Callbacks bound to widgets that were destroyed meanwhile are skipped.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot

from ...core.task_manager import CancelToken

log = logging.getLogger(__name__)
_live: set = set()


class _Bridge(QObject):
    progress = Signal(object)
    finished = Signal(object)
    error = Signal(object)

    def __init__(self, worker: "Worker"):
        super().__init__()
        self.worker = worker
        self.on_done = self.on_error = self.on_progress = None
        self.progress.connect(self._progress, Qt.QueuedConnection)
        self.finished.connect(self._finished, Qt.QueuedConnection)
        self.error.connect(self._error, Qt.QueuedConnection)

    @staticmethod
    def _call(cb, arg):
        if cb is None:
            return
        try:
            cb(arg)
        except RuntimeError as e:  # widget deleted while the task ran
            if "already deleted" not in str(e):
                log.exception("callback failed")
        except Exception:
            log.exception("callback failed")

    @Slot(object)
    def _progress(self, v):
        self._call(self.on_progress, v)

    @Slot(object)
    def _finished(self, v):
        self._call(self.on_done, v)
        _live.discard(self.worker)

    @Slot(object)
    def _error(self, e):
        if self.on_error is None:
            log.error("background task failed: %s", e)
        self._call(self.on_error, e)
        _live.discard(self.worker)


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args, with_progress: bool = False, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.bridge = _Bridge(self)
        self.token = CancelToken()
        self.with_progress = with_progress
        self.setAutoDelete(False)  # Python owns the object; released after delivery

    def run(self) -> None:
        try:
            if self.with_progress:
                self.kwargs["progress"] = self.bridge.progress.emit
            result = self.fn(*self.args, **self.kwargs)
        except BaseException as e:  # noqa: BLE001 - surface every failure to the UI
            log.debug("worker failed: %s", traceback.format_exc())
            self.bridge.error.emit(e)
        else:
            self.bridge.finished.emit(result)


def run_async(fn: Callable[..., Any], *args, on_done: Callable[[Any], None] | None = None,
              on_error: Callable[[BaseException], None] | None = None,
              on_progress: Callable[[Any], None] | None = None, **kwargs) -> Worker:
    w = Worker(fn, *args, with_progress=on_progress is not None, **kwargs)
    w.bridge.on_done, w.bridge.on_error, w.bridge.on_progress = on_done, on_error, on_progress
    _live.add(w)
    QThreadPool.globalInstance().start(w)
    return w
