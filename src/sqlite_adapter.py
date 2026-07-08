from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from storage_adapter import StorageAdapter


DEFAULT_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id TEXT,
    reader_id TEXT,
    antenna TEXT,
    event_type TEXT,
    event_time TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_event_time ON events(event_time);
CREATE INDEX IF NOT EXISTS idx_events_tag_id ON events(tag_id);
"""


class SQLiteAdapter(StorageAdapter):
    def __init__(self, database_path: str, schema_path: Optional[str] = None) -> None:
        self.database_path = database_path
        self.schema_path = schema_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._initialize_schema()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def store_event(self, event: Dict[str, Any]) -> None:
        if self._conn is None:
            raise RuntimeError("SQLite adapter is not connected")

        payload = json.dumps(event, ensure_ascii=True)

        self._conn.execute(
            """
            INSERT INTO events (tag_id, reader_id, antenna, event_type, event_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("tag_id"),
                event.get("reader_id"),
                event.get("antenna"),
                event.get("event_type"),
                event["event_time"],
                payload,
            ),
        )
        self._conn.commit()

    def _initialize_schema(self) -> None:
        if self._conn is None:
            raise RuntimeError("SQLite adapter is not connected")

        if self.schema_path:
            schema_file = Path(self.schema_path)
            if schema_file.exists():
                self._conn.executescript(schema_file.read_text(encoding="utf-8"))
                return

        self._conn.executescript(DEFAULT_SCHEMA)
