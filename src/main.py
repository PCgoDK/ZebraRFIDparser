from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

from dedup_storage_adapter import DuplicateFilteringStorageAdapter
from gui_server import start_gui_server
from llrp_adapter import LLRPAdapterServer, LLRPReaderClient
from parser import parse_event
from status_tracker import StatusTracker
from storage_factory import create_storage_adapter
from tcp_server import RFIDTCPServer


def _load_config(config_path: str) -> Dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _setup_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _get_key_fields(raw: Any) -> Iterable[str]:
    if isinstance(raw, list) and raw:
        return [str(item) for item in raw]
    return ["tag_id", "reader_id", "antenna"]


def main() -> None:
    default_config = Path(__file__).resolve().parents[1] / "config" / "config.json"

    parser = argparse.ArgumentParser(description="RFID Event Collector")
    parser.add_argument("--config", default=str(default_config), help="Path to config file")
    args = parser.parse_args()

    config = _load_config(args.config)
    _setup_logging(str(config.get("log_level", "INFO")))
    logger = logging.getLogger("rfid_event_collector")
    status_tracker = StatusTracker()

    def _status_callback(
        sender_id: str,
        protocol: str,
        raw_payload: Any = None,
        event: Any = None,
        error_stage: Any = None,
        error_message: Any = None,
    ) -> None:
        if raw_payload is not None:
            status_tracker.record_raw(sender_id=sender_id, protocol=protocol, raw_payload=str(raw_payload))
        if event is not None and isinstance(event, dict):
            status_tracker.record_event(sender_id=sender_id, protocol=protocol, event=event)
        if error_message is not None:
            status_tracker.record_error(
                sender_id=sender_id,
                protocol=protocol,
                error_stage=str(error_stage or "other"),
                error_message=str(error_message),
            )

    storage_adapter = create_storage_adapter(config.get("storage", {}))
    dedup_config = config.get("duplicate_filter", {})
    dedup_enabled = bool(dedup_config.get("enabled", True))
    if dedup_enabled:
        storage_adapter = DuplicateFilteringStorageAdapter(
            inner=storage_adapter,
            window_seconds=float(dedup_config.get("window_seconds", 2.0)),
            key_fields=_get_key_fields(dedup_config.get("key_fields")),
            metrics_log_interval_seconds=float(dedup_config.get("metrics_log_interval_seconds", 30.0)),
            logger=logger,
        )
    storage_adapter.connect()

    gui_service = None
    gui_config = config.get("gui", {})
    if bool(gui_config.get("enabled", True)):
        gui_service = start_gui_server(
            config_path=args.config,
            status_tracker=status_tracker,
            logger=logger,
            host=str(gui_config.get("host", "127.0.0.1")),
            port=int(gui_config.get("port", 8088)),
        )

    parser_config = config.get("parser_setup", {})

    input_config = config.get("input", {})
    protocol = str(input_config.get("protocol", "text_tcp")).strip().lower()

    # Backward compatibility for older config files.
    tcp_config = config.get("tcp_server", {})
    host = str(input_config.get("host", tcp_config.get("host", "0.0.0.0")))
    port = int(input_config.get("port", tcp_config.get("port", 9000)))

    if protocol == "llrp_client":
        reader_host = str(input_config.get("reader_host", "127.0.0.1"))
        reader_port = int(input_config.get("reader_port", 5084))
        reader_id = str(input_config.get("reader_id", reader_host))
        reconnect_delay_seconds = float(input_config.get("reconnect_delay_seconds", 2.0))
        socket_timeout_seconds = float(input_config.get("socket_timeout_seconds", 5.0))

        server = LLRPReaderClient(
            reader_host=reader_host,
            reader_port=reader_port,
            storage_adapter=storage_adapter,
            logger=logger,
            reader_id=reader_id,
            reconnect_delay_seconds=reconnect_delay_seconds,
            socket_timeout_seconds=socket_timeout_seconds,
            status_callback=_status_callback,
        )
    elif protocol == "llrp_server" or protocol == "llrp":
        reader_id = str(input_config.get("reader_id", "fx7500"))
        server = LLRPAdapterServer(
            host=host,
            port=port,
            storage_adapter=storage_adapter,
            logger=logger,
            reader_id=reader_id,
            status_callback=_status_callback,
        )
    elif protocol == "text_tcp":
        default_reader_id = str(input_config.get("reader_id", "")).strip() or None
        server = RFIDTCPServer(
            host=host,
            port=port,
            parser_func=lambda line: parse_event(
                line,
                parser_config=parser_config,
                default_reader_id=default_reader_id,
            ),
            storage_adapter=storage_adapter,
            logger=logger,
            status_callback=_status_callback,
        )
    else:
        raise ValueError(f"Unsupported input protocol: {protocol}")

    stop_event = threading.Event()

    def _handle_signal(signum: int, _frame: Any) -> None:
        logger.info("Received signal %s", signum)
        stop_event.set()
        server.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        server.serve_forever()
    finally:
        if gui_service is not None:
            gui_service.shutdown()
        storage_adapter.close()
        logger.info("RFID Event Collector stopped")


if __name__ == "__main__":
    main()
