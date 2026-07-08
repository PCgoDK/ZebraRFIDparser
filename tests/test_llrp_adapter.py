from __future__ import annotations

import struct

from llrp_adapter import (
    KEEPALIVE,
    KEEPALIVE_ACK,
    RO_ACCESS_REPORT,
    build_llrp_message,
    get_llrp_message_id,
    get_llrp_message_type,
    parse_llrp_message,
)


def _build_tlv(param_type: int, value: bytes) -> bytes:
    header = struct.pack("!H", param_type & 0x03FF)
    length = struct.pack("!H", 4 + len(value))
    return header + length + value


def _build_tv(param_type: int, value: bytes) -> bytes:
    return bytes([0x80 | (param_type & 0x7F)]) + value


def _build_llrp_message(message_type: int, body: bytes, message_id: int = 1) -> bytes:
    version_and_type = ((1 & 0x07) << 10) | (message_type & 0x03FF)
    total_length = 10 + len(body)
    return struct.pack("!HII", version_and_type, total_length, message_id) + body


def test_parse_ro_access_report_with_epc_data() -> None:
    epc = bytes.fromhex("E2000017221101441890ABCD")
    epc_data = _build_tlv(241, struct.pack("!H", len(epc) * 8) + epc)
    antenna = _build_tv(1, struct.pack("!H", 2))
    timestamp = _build_tv(2, struct.pack("!Q", 1_720_000_000_000_000))
    rssi = _build_tv(6, struct.pack("!b", -45))
    seen_count = _build_tv(8, struct.pack("!H", 3))

    tag_report_data = _build_tlv(240, epc_data + antenna + timestamp + rssi + seen_count)
    message = _build_llrp_message(RO_ACCESS_REPORT, tag_report_data)

    events = parse_llrp_message(message, reader_id="fx7500")

    assert len(events) == 1
    event = events[0]
    assert event["tag_id"] == "E2000017221101441890ABCD"
    assert event["reader_id"] == "fx7500"
    assert event["antenna"] == "2"
    assert event["rssi"] == -45
    assert event["seen_count"] == 3
    assert event["event_type"] == "scan"
    assert "event_time" in event


def test_parse_non_report_message_returns_empty() -> None:
    body = b"\x00\x00"
    message = _build_llrp_message(63, body)
    events = parse_llrp_message(message, reader_id="fx7500")
    assert events == []


def test_parse_invalid_length_returns_empty() -> None:
    valid_message = _build_llrp_message(RO_ACCESS_REPORT, b"")
    broken = valid_message[:-1]
    events = parse_llrp_message(broken, reader_id="fx7500")
    assert events == []


def test_message_helpers_extract_type_and_id() -> None:
    msg = build_llrp_message(KEEPALIVE, 1234)
    assert get_llrp_message_type(msg) == KEEPALIVE
    assert get_llrp_message_id(msg) == 1234


def test_build_keepalive_ack_message() -> None:
    ack = build_llrp_message(KEEPALIVE_ACK, 99)
    assert get_llrp_message_type(ack) == KEEPALIVE_ACK
    assert get_llrp_message_id(ack) == 99
    assert len(ack) == 10
