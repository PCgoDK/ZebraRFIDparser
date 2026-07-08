from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlite_adapter import SQLiteAdapter


def test_sqlite_adapter_creates_db_and_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "rfid.db"
    adapter = SQLiteAdapter(database_path=str(db_path), schema_path=None)

    adapter.connect()
    adapter.close()

    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "events"
    finally:
        conn.close()


def test_sqlite_adapter_store_event_persists_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "rfid.db"
    adapter = SQLiteAdapter(database_path=str(db_path), schema_path=None)

    adapter.connect()
    try:
        event = {
            "tag_id": "ABC123",
            "reader_id": "R1",
            "antenna": "1",
            "event_type": "scan",
            "event_time": "2026-07-08T12:00:00Z",
        }
        adapter.store_event(event)
    finally:
        adapter.close()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT tag_id, reader_id, antenna, event_type, event_time, raw_payload FROM events"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "ABC123"
        assert row[1] == "R1"
        assert row[2] == "1"
        assert row[3] == "scan"
        assert row[4] == "2026-07-08T12:00:00Z"

        payload = json.loads(row[5])
        assert payload["tag_id"] == "ABC123"
    finally:
        conn.close()


def test_sqlite_adapter_store_event_without_connect_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "rfid.db"
    adapter = SQLiteAdapter(database_path=str(db_path), schema_path=None)

    try:
        adapter.store_event({"event_time": "2026-07-08T12:00:00Z"})
        assert False, "Expected RuntimeError when adapter is not connected"
    except RuntimeError as exc:
        assert "not connected" in str(exc)
