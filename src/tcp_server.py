from __future__ import annotations

import logging
import socketserver
from typing import Any, Callable, Dict, Optional

from storage_adapter import StorageAdapter


class _RFIDRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server = self.server
        parse_event = getattr(server, "parse_event")
        storage_adapter = getattr(server, "storage_adapter")
        logger = getattr(server, "logger")
        status_callback = getattr(server, "status_callback")

        client_host, client_port = self.client_address
        logger.info("Client connected: %s:%s", client_host, client_port)

        while True:
            raw = self.rfile.readline()
            if not raw:
                break

            try:
                line = raw.decode("utf-8", errors="replace")
                if status_callback is not None:
                    status_callback(
                        sender_id=f"{client_host}:{client_port}",
                        protocol="text_tcp",
                        raw_payload=line,
                        event=None,
                    )
                try:
                    event = parse_event(line)
                except Exception as exc:
                    if status_callback is not None:
                        status_callback(
                            sender_id=f"{client_host}:{client_port}",
                            protocol="text_tcp",
                            raw_payload=None,
                            event=None,
                            error_stage="parse",
                            error_message=str(exc),
                        )
                    logger.exception("Failed to parse payload from %s:%s: %s", client_host, client_port, exc)
                    continue

                try:
                    storage_adapter.store_event(event)
                except Exception as exc:
                    if status_callback is not None:
                        status_callback(
                            sender_id=f"{client_host}:{client_port}",
                            protocol="text_tcp",
                            raw_payload=None,
                            event=None,
                            error_stage="storage",
                            error_message=str(exc),
                        )
                    logger.exception("Failed to store event from %s:%s: %s", client_host, client_port, exc)
                    continue

                if status_callback is not None:
                    status_callback(
                        sender_id=f"{client_host}:{client_port}",
                        protocol="text_tcp",
                        raw_payload=None,
                        event=event,
                    )
                logger.debug("Event stored from %s:%s -> %s", client_host, client_port, event)
            except Exception as exc:
                logger.exception("Failed to process payload from %s:%s: %s", client_host, client_port, exc)

        logger.info("Client disconnected: %s:%s", client_host, client_port)


class _ThreadedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class RFIDTCPServer:
    def __init__(
        self,
        host: str,
        port: int,
        parser_func: Callable[[str], Dict[str, Any]],
        storage_adapter: StorageAdapter,
        logger: logging.Logger,
        status_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.parser_func = parser_func
        self.storage_adapter = storage_adapter
        self.logger = logger
        self.status_callback = status_callback
        self._server = _ThreadedTCPServer((self.host, self.port), _RFIDRequestHandler)
        self._server.parse_event = self.parser_func
        self._server.storage_adapter = self.storage_adapter
        self._server.logger = self.logger
        self._server.status_callback = self.status_callback

    def serve_forever(self) -> None:
        self.logger.info("Starting RFID TCP server on %s:%s", self.host, self.port)
        self._server.serve_forever()

    def shutdown(self) -> None:
        self.logger.info("Shutting down RFID TCP server")
        self._server.shutdown()
        self._server.server_close()
