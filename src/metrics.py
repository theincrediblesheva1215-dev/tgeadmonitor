from __future__ import annotations

import logging
from collections import Counter
from threading import Lock

log = logging.getLogger("metrics")


class Metrics:
    def __init__(self) -> None:
        self._counters: Counter[str] = Counter()
        self._lock = Lock()

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def log_summary(self) -> None:
        log.info("METRICS %s", self.snapshot())