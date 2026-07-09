from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from storage_adapter import StorageAdapter


class CSVAdapter(StorageAdapter):
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self._file: Optional[TextIO] = None
        self._writer: Optional[csv.DictWriter[str]] = None

    def connect(self) -> None:
        path = Path(self.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = path.exists()

        self._file = path.open("a", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(
            self._file,
            fieldnames=[
                "tag_id",
                "reader_id",
                "antenna",
                "event_type",
                "event_time",
                "raw_payload",
            ],
        )

        if not file_exists or path.stat().st_size == 0:
            self._writer.writeheader()
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None

    def store_event(self, event: Dict[str, Any]) -> None:
        if self._file is None or self._writer is None:
            raise RuntimeError("CSV adapter is not connected")

        self._writer.writerow(
            {
                "tag_id": event.get("tag_id", ""),
                "reader_id": event.get("reader_id", ""),
                "antenna": event.get("antenna", ""),
                "event_type": event.get("event_type", ""),
                "event_time": event["event_time"],
                "raw_payload": json.dumps(event, ensure_ascii=True),
            }
        )
        self._file.flush()