from __future__ import annotations

import csv
import json
from pathlib import Path

from csv_adapter import CSVAdapter


def test_csv_adapter_creates_file_with_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "events.csv"
    adapter = CSVAdapter(file_path=str(csv_path))

    adapter.connect()
    adapter.close()

    assert csv_path.exists()
    rows = list(csv.reader(csv_path.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["tag_id", "reader_id", "antenna", "event_type", "event_time", "raw_payload"]


def test_csv_adapter_store_event_writes_row(tmp_path: Path) -> None:
    csv_path = tmp_path / "events.csv"
    adapter = CSVAdapter(file_path=str(csv_path))

    adapter.connect()
    try:
        adapter.store_event(
            {
                "tag_id": "E2000017221101441890ABCD",
                "reader_id": "R1",
                "antenna": "1",
                "event_type": "scan",
                "event_time": "2026-07-09T08:00:00Z",
            }
        )
    finally:
        adapter.close()

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["tag_id"] == "E2000017221101441890ABCD"
    assert rows[0]["reader_id"] == "R1"
    assert rows[0]["event_time"] == "2026-07-09T08:00:00Z"

    payload = json.loads(rows[0]["raw_payload"])
    assert payload["tag_id"] == "E2000017221101441890ABCD"


def test_csv_adapter_store_event_without_connect_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "events.csv"
    adapter = CSVAdapter(file_path=str(csv_path))

    try:
        adapter.store_event({"event_time": "2026-07-09T08:00:00Z"})
        assert False, "Expected RuntimeError when adapter is not connected"
    except RuntimeError as exc:
        assert "not connected" in str(exc)