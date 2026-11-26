"""A tiny thread-safe publish/subscribe bus decoupling services from the UI."""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

log = logging.getLogger(__name__)
Handler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._handlers[topic]:
                    self._handlers[topic].remove(handler)

        return unsubscribe

    def publish(self, topic: str, **payload: Any) -> None:
        with self._lock:
            handlers = list(self._handlers.get(topic, ())) + list(self._handlers.get("*", ()))
        for h in handlers:
            try:
                h({"topic": topic, **payload})
            except Exception:  # a bad subscriber must never break publishers
                log.exception("event handler failed for %s", topic)
