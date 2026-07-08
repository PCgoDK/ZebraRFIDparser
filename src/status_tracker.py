from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class StatusTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._senders: Dict[str, Dict[str, Any]] = {}
        self._total_raw_messages = 0
        self._total_events = 0
        self._total_errors = 0

    def _get_or_create_sender(self, sender_id: str, protocol: str, now: str) -> Dict[str, Any]:
        entry = self._senders.setdefault(
            sender_id,
            {
                "sender_id": sender_id,
                "protocol": protocol,
                "first_seen": now,
                "last_seen": now,
                "raw_messages": 0,
                "events": 0,
                "parse_errors": 0,
                "storage_errors": 0,
                "other_errors": 0,
                "last_error": None,
                "last_error_stage": None,
                "last_error_time": None,
                "last_tag_id": None,
                "last_event_time": None,
                "last_payload_preview": None,
            },
        )
        entry["protocol"] = protocol
        entry["last_seen"] = now
        return entry

    def record_raw(self, sender_id: str, protocol: str, raw_payload: Optional[str] = None) -> None:
        now = _utc_now_iso()
        with self._lock:
            entry = self._get_or_create_sender(sender_id=sender_id, protocol=protocol, now=now)
            entry["raw_messages"] += 1
            if raw_payload:
                entry["last_payload_preview"] = raw_payload[:140]
            self._total_raw_messages += 1

    def record_event(self, sender_id: str, protocol: str, event: Dict[str, Any]) -> None:
        now = _utc_now_iso()
        with self._lock:
            entry = self._get_or_create_sender(sender_id=sender_id, protocol=protocol, now=now)
            entry["events"] += 1
            entry["last_tag_id"] = event.get("tag_id")
            entry["last_event_time"] = event.get("event_time")
            self._total_events += 1

    def record_error(
        self,
        sender_id: str,
        protocol: str,
        error_stage: str,
        error_message: str,
    ) -> None:
        now = _utc_now_iso()
        with self._lock:
            entry = self._get_or_create_sender(sender_id=sender_id, protocol=protocol, now=now)
            stage = str(error_stage).strip().lower()
            if stage == "parse":
                entry["parse_errors"] += 1
            elif stage == "storage":
                entry["storage_errors"] += 1
            else:
                entry["other_errors"] += 1

            entry["last_error"] = str(error_message)[:300]
            entry["last_error_stage"] = stage or "other"
            entry["last_error_time"] = now
            self._total_errors += 1

    def snapshot(self, limit: int = 25) -> Dict[str, Any]:
        with self._lock:
            rows: List[Dict[str, Any]] = list(self._senders.values())

        rows.sort(key=lambda item: str(item.get("last_seen", "")), reverse=True)
        latest = rows[: max(1, limit)]
        return {
            "generated_at": _utc_now_iso(),
            "total_senders": len(rows),
            "total_raw_messages": self._total_raw_messages,
            "total_events": self._total_events,
            "total_errors": self._total_errors,
            "latest_senders": latest,
        }
