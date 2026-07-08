from __future__ import annotations

from parser import parse_event


def test_parse_json_event_with_defaults() -> None:
    event = parse_event('{"tag_id":"ABC123","reader_id":"R1"}')

    assert event["tag_id"] == "ABC123"
    assert event["reader_id"] == "R1"
    assert event["event_type"] == "scan"
    assert "event_time" in event


def test_parse_json_event_missing_tag_id_raises() -> None:
    try:
        parse_event('{"reader_id":"R1"}')
        assert False, "Expected ValueError for missing tag_id"
    except ValueError as exc:
        assert "tag_id" in str(exc)


def test_parse_key_value_event() -> None:
    event = parse_event("tag_id=ABC123,reader_id=R2,antenna=1")

    assert event["tag_id"] == "ABC123"
    assert event["reader_id"] == "R2"
    assert event["antenna"] == "1"
    assert event["event_type"] == "scan"


def test_parse_plain_tag_id_fallback() -> None:
    event = parse_event("E2000017221101441890ABCD")

    assert event["tag_id"] == "E2000017221101441890ABCD"
    assert event["event_type"] == "scan"
    assert "event_time" in event


def test_parse_with_key_aliases() -> None:
    config = {
        "key_aliases": {
            "epc": "tag_id",
            "reader": "reader_id",
            "antenna_index": "antenna",
            "signal_strength": "rssi",
            "timestamp": "event_time",
        }
    }
    event = parse_event('{"epc":"ABC123","reader":"R1","antenna_index":2,"signal_strength":-42,"timestamp":"2026-07-08T16:00:00Z"}', parser_config=config)

    assert event["tag_id"] == "ABC123"
    assert event["reader_id"] == "R1"
    assert event["antenna"] == 2
    assert event["rssi"] == -42
    assert event["event_time"] == "2026-07-08T16:00:00Z"


def test_parse_with_default_reader_id() -> None:
    config = {
        "key_aliases": {
            "epc": "tag_id",
        }
    }
    event = parse_event('{"epc":"ABC123"}', parser_config=config, default_reader_id="R1")

    assert event["tag_id"] == "ABC123"
    assert event["reader_id"] == "R1"


def test_plain_tag_fallback_can_be_disabled() -> None:
    config = {"allow_plain_tag_id": False}
    try:
        parse_event("E2000017221101441890ABCD", parser_config=config)
        assert False, "Expected ValueError when plain fallback is disabled"
    except ValueError as exc:
        assert "disabled" in str(exc)
