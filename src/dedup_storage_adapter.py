from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from storage_adapter import StorageAdapter


class DuplicateFilteringStorageAdapter(StorageAdapter):
    """Drops duplicate EPC events within a configurable time window."""

    def __init__(
        self,
        inner: StorageAdapter,
        window_seconds: float = 2.0,
        key_fields: Iterable[str] = ("tag_id", "reader_id", "antenna"),
        metrics_log_interval_seconds: Optional[float] = 30.0,
        logger: Optional[logging.Logger] = None,
        time_func: Optional[Callable[[], float]] = None,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")

        self.inner = inner
        self.window_seconds = float(window_seconds)
        self.key_fields = tuple(key_fields)
        if metrics_log_interval_seconds is not None and metrics_log_interval_seconds <= 0:
            raise ValueError("metrics_log_interval_seconds must be > 0 when provided")
        self.metrics_log_interval_seconds = metrics_log_interval_seconds
        self.logger = logger or logging.getLogger("rfid_event_collector.dedup")
        self.time_func = time_func or time.monotonic

        self._lock = threading.Lock()
        self._last_seen: Dict[Tuple[str, ...], float] = {}
        self._next_prune_time = 0.0
        now = self.time_func()
        self._next_metrics_log_time = (
            now + self.metrics_log_interval_seconds
            if self.metrics_log_interval_seconds is not None
            else float("inf")
        )
        self._received_count = 0
        self._stored_count = 0
        self._dropped_duplicate_count = 0

    def connect(self) -> None:
        self.inner.connect()

    def close(self) -> None:
        self.inner.close()

    def store_event(self, event: Dict[str, Any]) -> None:
        now = self.time_func()
        with self._lock:
            self._received_count += 1

        epc = event.get("tag_id")
        if epc in (None, ""):
            self.inner.store_event(event)
            with self._lock:
                self._stored_count += 1
                self._maybe_log_metrics(now)
            return

        key = self._build_key(event)

        with self._lock:
            self._prune_if_needed(now)
            previous = self._last_seen.get(key)
            if previous is not None and (now - previous) < self.window_seconds:
                self._dropped_duplicate_count += 1
                self.logger.debug("Dropped duplicate EPC event: key=%s", key)
                self._maybe_log_metrics(now)
                return

            # Reserve the key before writing to avoid race duplicates.
            self._last_seen[key] = now

        try:
            self.inner.store_event(event)
        except Exception:
            # Remove reservation when write fails so retries are not blocked.
            with self._lock:
                if self._last_seen.get(key) == now:
                    self._last_seen.pop(key, None)
            raise
        else:
            with self._lock:
                self._stored_count += 1
                self._maybe_log_metrics(now)

    def _build_key(self, event: Dict[str, Any]) -> Tuple[str, ...]:
        return tuple(str(event.get(field, "")) for field in self.key_fields)

    def _prune_if_needed(self, now: float) -> None:
        if now < self._next_prune_time:
            return

        threshold = now - self.window_seconds
        stale_keys = [key for key, ts in self._last_seen.items() if ts < threshold]
        for key in stale_keys:
            self._last_seen.pop(key, None)

        self._next_prune_time = now + max(1.0, self.window_seconds)

    def _maybe_log_metrics(self, now: float) -> None:
        if now < self._next_metrics_log_time:
            return

        self.logger.info(
            "Dedup metrics: received=%s stored=%s dropped_duplicates=%s active_keys=%s window_seconds=%s",
            self._received_count,
            self._stored_count,
            self._dropped_duplicate_count,
            len(self._last_seen),
            self.window_seconds,
        )
        if self.metrics_log_interval_seconds is None:
            self._next_metrics_log_time = float("inf")
        else:
            self._next_metrics_log_time = now + self.metrics_log_interval_seconds
