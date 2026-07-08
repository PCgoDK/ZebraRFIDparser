from __future__ import annotations

import logging
import math
import socket
import socketserver
import struct
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from storage_adapter import StorageAdapter


RO_ACCESS_REPORT = 61
KEEPALIVE = 62
KEEPALIVE_ACK = 72
PARAM_TAG_REPORT_DATA = 240
PARAM_EPC_DATA = 241


_TV_PARAM_LENGTHS = {
    1: 2,   # AntennaID
    2: 8,   # FirstSeenTimestampUTC
    3: 8,   # FirstSeenTimestampUptime
    4: 8,   # LastSeenTimestampUTC
    5: 8,   # LastSeenTimestampUptime
    6: 1,   # PeakRSSI
    7: 2,   # ChannelIndex
    8: 2,   # TagSeenCount
    9: 4,   # ROSpecID
    10: 2,  # InventoryParameterSpecID
    11: 2,  # C1G2PC
    12: 2,  # C1G2CRC
    13: 12, # EPC-96
    14: 2,  # SpecIndex
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_micros_to_iso(value: int) -> str:
    dt = datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_llrp_parameters(data: bytes) -> List[Dict[str, Any]]:
    params: List[Dict[str, Any]] = []
    index = 0
    data_len = len(data)

    while index < data_len:
        first_byte = data[index]

        # TV parameter: 1 byte header where MSB is 1.
        if first_byte & 0x80:
            param_type = first_byte & 0x7F
            value_len = _TV_PARAM_LENGTHS.get(param_type)
            if value_len is None or index + 1 + value_len > data_len:
                break

            value = data[index + 1 : index + 1 + value_len]
            params.append(
                {
                    "encoding": "tv",
                    "type": param_type,
                    "value": value,
                    "raw": data[index : index + 1 + value_len],
                }
            )
            index += 1 + value_len
            continue

        # TLV parameter: 2-byte type field + 2-byte total length.
        if index + 4 > data_len:
            break

        param_header = struct.unpack("!H", data[index : index + 2])[0]
        param_type = param_header & 0x03FF
        total_len = struct.unpack("!H", data[index + 2 : index + 4])[0]

        if total_len < 4 or index + total_len > data_len:
            break

        value = data[index + 4 : index + total_len]
        params.append(
            {
                "encoding": "tlv",
                "type": param_type,
                "value": value,
                "raw": data[index : index + total_len],
            }
        )
        index += total_len

    return params


def _extract_epc_from_epc_data(value: bytes) -> Optional[str]:
    if len(value) < 2:
        return None

    bit_length = struct.unpack("!H", value[:2])[0]
    byte_length = int(math.ceil(bit_length / 8.0))
    epc = value[2 : 2 + byte_length]

    if len(epc) != byte_length:
        return None

    return epc.hex().upper()


def _extract_tag_event(tag_report_data: bytes, reader_id: str) -> Optional[Dict[str, Any]]:
    params = _parse_llrp_parameters(tag_report_data)

    tag_id: Optional[str] = None
    antenna: Optional[str] = None
    event_time: Optional[str] = None
    rssi: Optional[int] = None
    seen_count: Optional[int] = None

    for param in params:
        param_type = param["type"]
        value = param["value"]
        encoding = param["encoding"]

        if encoding == "tlv" and param_type == PARAM_EPC_DATA:
            tag_id = _extract_epc_from_epc_data(value)
            continue

        if encoding == "tv" and param_type == 13 and len(value) == 12:
            tag_id = value.hex().upper()
            continue

        if encoding == "tv" and param_type == 1 and len(value) == 2:
            antenna = str(struct.unpack("!H", value)[0])
            continue

        if encoding == "tv" and param_type in (2, 4) and len(value) == 8:
            event_time = _utc_micros_to_iso(struct.unpack("!Q", value)[0])
            continue

        if encoding == "tv" and param_type == 6 and len(value) == 1:
            rssi = struct.unpack("!b", value)[0]
            continue

        if encoding == "tv" and param_type == 8 and len(value) == 2:
            seen_count = struct.unpack("!H", value)[0]
            continue

    if not tag_id:
        return None

    event: Dict[str, Any] = {
        "tag_id": tag_id,
        "reader_id": reader_id,
        "event_type": "scan",
        "event_time": event_time or _utc_now_iso(),
    }

    if antenna is not None:
        event["antenna"] = antenna
    if rssi is not None:
        event["rssi"] = rssi
    if seen_count is not None:
        event["seen_count"] = seen_count

    return event


def parse_llrp_message(message: bytes, reader_id: str) -> List[Dict[str, Any]]:
    if len(message) < 10:
        return []

    message_type = struct.unpack("!H", message[:2])[0] & 0x03FF
    message_len = struct.unpack("!I", message[2:6])[0]
    if message_len != len(message):
        return []

    if message_type != RO_ACCESS_REPORT:
        return []

    body = message[10:]
    params = _parse_llrp_parameters(body)

    events: List[Dict[str, Any]] = []
    for param in params:
        if param["encoding"] == "tlv" and param["type"] == PARAM_TAG_REPORT_DATA:
            event = _extract_tag_event(param["value"], reader_id=reader_id)
            if event is not None:
                events.append(event)

    return events


def get_llrp_message_type(message: bytes) -> Optional[int]:
    if len(message) < 10:
        return None
    return struct.unpack("!H", message[:2])[0] & 0x03FF


def get_llrp_message_id(message: bytes) -> Optional[int]:
    if len(message) < 10:
        return None
    return struct.unpack("!I", message[6:10])[0]


def build_llrp_message(message_type: int, message_id: int, payload: bytes = b"") -> bytes:
    version_and_type = ((1 & 0x07) << 10) | (message_type & 0x03FF)
    total_length = 10 + len(payload)
    return struct.pack("!HII", version_and_type, total_length, message_id) + payload


class _LLRPRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        storage_adapter = getattr(server, "storage_adapter")
        logger = getattr(server, "logger")
        reader_id = getattr(server, "reader_id")
        status_callback = getattr(server, "status_callback")

        client_host, client_port = self.client_address
        logger.info("LLRP client connected: %s:%s", client_host, client_port)

        buffer = b""

        while True:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            buffer += chunk

            while len(buffer) >= 10:
                frame_len = struct.unpack("!I", buffer[2:6])[0]
                if frame_len < 10:
                    logger.error("Invalid LLRP frame length: %s", frame_len)
                    buffer = b""
                    break

                if len(buffer) < frame_len:
                    break

                frame = buffer[:frame_len]
                buffer = buffer[frame_len:]

                try:
                    if status_callback is not None:
                        status_callback(
                            sender_id=f"{client_host}:{client_port}",
                            protocol="llrp_server",
                            raw_payload=f"frame_len={frame_len}",
                            event=None,
                        )
                    events = parse_llrp_message(frame, reader_id=reader_id)
                    for event in events:
                        try:
                            storage_adapter.store_event(event)
                        except Exception as exc:
                            if status_callback is not None:
                                status_callback(
                                    sender_id=f"{client_host}:{client_port}",
                                    protocol="llrp_server",
                                    raw_payload=None,
                                    event=None,
                                    error_stage="storage",
                                    error_message=str(exc),
                                )
                            raise
                        if status_callback is not None:
                            status_callback(
                                sender_id=f"{client_host}:{client_port}",
                                protocol="llrp_server",
                                raw_payload=None,
                                event=event,
                            )
                        logger.debug("Stored LLRP event from %s:%s -> %s", client_host, client_port, event)
                except Exception as exc:
                    if status_callback is not None:
                        status_callback(
                            sender_id=f"{client_host}:{client_port}",
                            protocol="llrp_server",
                            raw_payload=None,
                            event=None,
                            error_stage="parse",
                            error_message=str(exc),
                        )
                    logger.exception("Failed to process LLRP frame from %s:%s: %s", client_host, client_port, exc)

        logger.info("LLRP client disconnected: %s:%s", client_host, client_port)


class _ThreadedLLRPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class LLRPAdapterServer:
    def __init__(
        self,
        host: str,
        port: int,
        storage_adapter: StorageAdapter,
        logger: logging.Logger,
        reader_id: str,
        status_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.storage_adapter = storage_adapter
        self.logger = logger
        self.reader_id = reader_id
        self.status_callback = status_callback

        self._server = _ThreadedLLRPServer((self.host, self.port), _LLRPRequestHandler)
        self._server.storage_adapter = self.storage_adapter
        self._server.logger = self.logger
        self._server.reader_id = self.reader_id
        self._server.status_callback = self.status_callback

    def serve_forever(self) -> None:
        self.logger.info("Starting LLRP adapter server on %s:%s", self.host, self.port)
        self._server.serve_forever()

    def shutdown(self) -> None:
        self.logger.info("Shutting down LLRP adapter server")
        self._server.shutdown()
        self._server.server_close()


class LLRPReaderClient:
    def __init__(
        self,
        reader_host: str,
        reader_port: int,
        storage_adapter: StorageAdapter,
        logger: logging.Logger,
        reader_id: str,
        reconnect_delay_seconds: float = 2.0,
        socket_timeout_seconds: float = 5.0,
        status_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self.reader_host = reader_host
        self.reader_port = reader_port
        self.storage_adapter = storage_adapter
        self.logger = logger
        self.reader_id = reader_id
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self.socket_timeout_seconds = socket_timeout_seconds
        self.status_callback = status_callback
        self._stop = False
        self._sock: Optional[socket.socket] = None

    def serve_forever(self) -> None:
        self.logger.info(
            "Starting LLRP reader client to %s:%s", self.reader_host, self.reader_port
        )

        while not self._stop:
            try:
                self._connect_and_consume()
            except Exception as exc:
                if self._stop:
                    break
                self.logger.exception(
                    "LLRP reader connection error (%s:%s): %s",
                    self.reader_host,
                    self.reader_port,
                    exc,
                )

            if not self._stop:
                time.sleep(self.reconnect_delay_seconds)

    def shutdown(self) -> None:
        self.logger.info("Shutting down LLRP reader client")
        self._stop = True
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _connect_and_consume(self) -> None:
        with socket.create_connection((self.reader_host, self.reader_port)) as sock:
            self._sock = sock
            self._sock.settimeout(self.socket_timeout_seconds)
            self.logger.info(
                "Connected to LLRP reader %s:%s", self.reader_host, self.reader_port
            )

            buffer = b""
            while not self._stop:
                try:
                    chunk = self._sock.recv(4096)
                except socket.timeout:
                    continue

                if not chunk:
                    self.logger.warning("LLRP reader closed connection")
                    break
                buffer += chunk

                while len(buffer) >= 10:
                    frame_len = struct.unpack("!I", buffer[2:6])[0]
                    if frame_len < 10:
                        self.logger.error("Invalid LLRP frame length from reader: %s", frame_len)
                        buffer = b""
                        break
                    if len(buffer) < frame_len:
                        break

                    frame = buffer[:frame_len]
                    buffer = buffer[frame_len:]
                    if self.status_callback is not None:
                        self.status_callback(
                            sender_id=self.reader_host,
                            protocol="llrp_client",
                            raw_payload=f"frame_len={frame_len}",
                            event=None,
                        )
                    try:
                        self._handle_frame(frame)
                    except Exception as exc:
                        if self.status_callback is not None:
                            self.status_callback(
                                sender_id=self.reader_host,
                                protocol="llrp_client",
                                raw_payload=None,
                                event=None,
                                error_stage="parse",
                                error_message=str(exc),
                            )
                        self.logger.exception("Failed to handle LLRP frame: %s", exc)

            self._sock = None

    def _handle_frame(self, frame: bytes) -> None:
        message_type = get_llrp_message_type(frame)
        if message_type is None:
            return

        if message_type == KEEPALIVE:
            message_id = get_llrp_message_id(frame)
            if message_id is not None and self._sock is not None:
                ack = build_llrp_message(KEEPALIVE_ACK, message_id)
                self._sock.sendall(ack)
                self.logger.debug("Sent KEEPALIVE_ACK with message id %s", message_id)
            return

        events = parse_llrp_message(frame, reader_id=self.reader_id)
        for event in events:
            try:
                self.storage_adapter.store_event(event)
            except Exception as exc:
                if self.status_callback is not None:
                    self.status_callback(
                        sender_id=self.reader_host,
                        protocol="llrp_client",
                        raw_payload=None,
                        event=None,
                        error_stage="storage",
                        error_message=str(exc),
                    )
                raise
            if self.status_callback is not None:
                self.status_callback(
                    sender_id=self.reader_host,
                    protocol="llrp_client",
                    raw_payload=None,
                    event=event,
                )
            self.logger.debug("Stored LLRP event from reader -> %s", event)
