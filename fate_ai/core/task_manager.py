"""Background task execution for long-running operations.

Work runs on a thread pool; results are delivered back through Qt signals when a
Qt application exists (so slots run on the GUI thread), otherwise via plain
callbacks. Tasks can be cancelled cooperatively through ``CancelToken``.
"""
from __future__ import annotations

import itertools
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass
class TaskInfo:
    id: int
    name: str
    token: CancelToken
    future: Future
    progress: float = 0.0
    status: str = "running"
    meta: dict[str, Any] = field(default_factory=dict)


class TaskManager:
    def __init__(self, max_workers: int = 8, event_bus=None) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fate")
        self._ids = itertools.count(1)
        self._tasks: dict[int, TaskInfo] = {}
        self._lock = threading.Lock()
        self._bus = event_bus

    def submit(self, name: str, fn: Callable[..., Any], *args,
               on_done: Callable[[Any], None] | None = None,
               on_error: Callable[[BaseException], None] | None = None,
               **kwargs) -> TaskInfo:
        """Run ``fn(*args, token=CancelToken, **kwargs)`` in the background."""
        token = CancelToken()
        tid = next(self._ids)

        def runner():
            return fn(*args, token=token, **kwargs)

        fut = self._pool.submit(runner)
        info = TaskInfo(tid, name, token, fut)
        with self._lock:
            self._tasks[tid] = info
        if self._bus:
            self._bus.publish("task.started", id=tid, name=name)

        def done(f: Future) -> None:
            exc = f.exception()
            info.status = "cancelled" if token.cancelled else ("failed" if exc else "done")
            with self._lock:
                self._tasks.pop(tid, None)
            if self._bus:
                self._bus.publish("task.finished", id=tid, name=name, status=info.status)
            try:
                if exc is not None:
                    if on_error:
                        on_error(exc)
                    else:
                        log.error("task %s failed: %s", name, exc)
                elif on_done:
                    on_done(f.result())
            except Exception:
                log.exception("task callback failed")

        fut.add_done_callback(done)
        return info

    def active(self) -> list[TaskInfo]:
        with self._lock:
            return list(self._tasks.values())

    def cancel_all(self) -> None:
        for t in self.active():
            t.token.cancel()

    def shutdown(self) -> None:
        self.cancel_all()
        self._pool.shutdown(wait=False, cancel_futures=True)
