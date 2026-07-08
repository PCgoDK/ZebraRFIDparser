from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_keys(payload: Dict[str, Any], key_aliases: Dict[str, str]) -> Dict[str, Any]:
    if not key_aliases:
        return payload

    normalized: Dict[str, Any] = {}
    for key, value in payload.items():
        mapped = key_aliases.get(str(key), str(key))
        normalized[mapped] = value
    return normalized


def parse_event(
    raw_line: str,
    parser_config: Optional[Dict[str, Any]] = None,
    default_reader_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse one incoming line into a normalized RFID event dict."""
    parser_config = parser_config or {}
    default_event_type = str(parser_config.get("default_event_type", "scan"))
    required_tag_field = str(parser_config.get("required_tag_field", "tag_id"))
    allow_plain_tag_id = bool(parser_config.get("allow_plain_tag_id", True))
    key_aliases_raw = parser_config.get("key_aliases", {})
    key_aliases = key_aliases_raw if isinstance(key_aliases_raw, dict) else {}

    line = raw_line.strip()
    if not line:
        raise ValueError("Empty event payload")

    # Preferred format: JSON payload.
    try:
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            event = _normalize_keys(dict(parsed), key_aliases)
            event.setdefault("event_time", _utc_now_iso())
            event.setdefault("event_type", default_event_type)
            event.setdefault("raw", line)
            if required_tag_field not in event:
                raise ValueError(f"JSON event missing required field: {required_tag_field}")
            if default_reader_id and event.get("reader_id") in (None, ""):
                event["reader_id"] = default_reader_id
            return event
    except json.JSONDecodeError:
        pass

    # Fallback format: key=value pairs separated by comma, semicolon, or spaces.
    normalized = line.replace(";", ",").replace(" ", ",")
    pairs = [part for part in normalized.split(",") if part]
    event: Dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        event[key.strip()] = value.strip()

    event = _normalize_keys(event, key_aliases)

    if event:
        if required_tag_field not in event:
            raise ValueError(f"Key-value event missing required field: {required_tag_field}")
        event.setdefault("event_time", _utc_now_iso())
        event.setdefault("event_type", default_event_type)
        event.setdefault("raw", line)
        if default_reader_id and event.get("reader_id") in (None, ""):
            event["reader_id"] = default_reader_id
        return event

    # Last fallback: treat line as plain RFID tag id.
    if not allow_plain_tag_id:
        raise ValueError("Plain tag fallback is disabled by parser configuration")

    return {
        required_tag_field: line,
        "event_type": default_event_type,
        "event_time": _utc_now_iso(),
        "raw": line,
        **({"reader_id": default_reader_id} if default_reader_id else {}),
    }
