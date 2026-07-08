from __future__ import annotations

from typing import Any, Dict, List

from dedup_storage_adapter import DuplicateFilteringStorageAdapter
from storage_adapter import StorageAdapter


class _InMemoryStorageAdapter(StorageAdapter):
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def store_event(self, event: Dict[str, Any]) -> None:
        self.events.append(dict(event))


class _FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def now(self) -> float:
        return self.value


class _FakeLogger:
    def __init__(self) -> None:
        self.infos: List[str] = []
        self.debugs: List[str] = []

    def info(self, message: str, *args: Any) -> None:
        self.infos.append(message % args if args else message)

    def debug(self, message: str, *args: Any) -> None:
        self.debugs.append(message % args if args else message)


def test_duplicate_event_dropped_within_window() -> None:
    inner = _InMemoryStorageAdapter()
    clock = _FakeClock()
    adapter = DuplicateFilteringStorageAdapter(
        inner=inner,
        window_seconds=2.0,
        key_fields=("tag_id", "reader_id", "antenna"),
        time_func=clock.now,
    )

    event = {
        "tag_id": "E2000017221101441890ABCD",
        "reader_id": "fx7500",
        "antenna": "1",
        "event_time": "2026-07-08T12:00:00Z",
    }

    adapter.store_event(event)
    clock.value += 1.0
    adapter.store_event(event)

    assert len(inner.events) == 1


def test_same_event_allowed_after_window() -> None:
    inner = _InMemoryStorageAdapter()
    clock = _FakeClock()
    adapter = DuplicateFilteringStorageAdapter(
        inner=inner,
        window_seconds=2.0,
        key_fields=("tag_id", "reader_id", "antenna"),
        time_func=clock.now,
    )

    event = {
        "tag_id": "E2000017221101441890ABCD",
        "reader_id": "fx7500",
        "antenna": "1",
        "event_time": "2026-07-08T12:00:00Z",
    }

    adapter.store_event(event)
    clock.value += 2.1
    adapter.store_event(event)

    assert len(inner.events) == 2


def test_events_without_tag_id_are_not_filtered() -> None:
    inner = _InMemoryStorageAdapter()
    clock = _FakeClock()
    adapter = DuplicateFilteringStorageAdapter(
        inner=inner,
        window_seconds=2.0,
        key_fields=("tag_id",),
        time_func=clock.now,
    )

    event = {
        "reader_id": "fx7500",
        "antenna": "1",
        "event_time": "2026-07-08T12:00:00Z",
    }

    adapter.store_event(event)
    adapter.store_event(event)

    assert len(inner.events) == 2


def test_different_reader_not_treated_as_duplicate() -> None:
    inner = _InMemoryStorageAdapter()
    clock = _FakeClock()
    adapter = DuplicateFilteringStorageAdapter(
        inner=inner,
        window_seconds=2.0,
        key_fields=("tag_id", "reader_id"),
        time_func=clock.now,
    )

    event_a = {
        "tag_id": "E2000017221101441890ABCD",
        "reader_id": "fx7500-a",
        "event_time": "2026-07-08T12:00:00Z",
    }
    event_b = {
        "tag_id": "E2000017221101441890ABCD",
        "reader_id": "fx7500-b",
        "event_time": "2026-07-08T12:00:00Z",
    }

    adapter.store_event(event_a)
    adapter.store_event(event_b)

    assert len(inner.events) == 2


def test_metrics_logged_every_interval_with_dropped_count() -> None:
    inner = _InMemoryStorageAdapter()
    clock = _FakeClock()
    logger = _FakeLogger()
    adapter = DuplicateFilteringStorageAdapter(
        inner=inner,
        window_seconds=2.0,
        key_fields=("tag_id", "reader_id", "antenna"),
        metrics_log_interval_seconds=5.0,
        logger=logger,
        time_func=clock.now,
    )

    event = {
        "tag_id": "E2000017221101441890ABCD",
        "reader_id": "fx7500",
        "antenna": "1",
        "event_time": "2026-07-08T12:00:00Z",
    }

    adapter.store_event(event)  # stored
    clock.value += 1.0
    adapter.store_event(event)  # dropped duplicate
    clock.value += 4.1
    adapter.store_event(event)  # periodic metrics log should trigger here

    assert len(inner.events) == 2
    assert any("dropped_duplicates=1" in line for line in logger.infos)
