from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from storage_adapter import StorageAdapter


class RESTAPIAdapter(StorageAdapter):
    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: float = 5.0,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        bearer_token: Optional[str] = None,
        payload_key: Optional[str] = None,
    ) -> None:
        if not endpoint_url:
            raise ValueError("endpoint_url is required for REST API adapter")

        self.endpoint_url = endpoint_url
        self.timeout_seconds = float(timeout_seconds)
        self.method = method.upper().strip() or "POST"
        self.headers = dict(headers or {})
        self.bearer_token = bearer_token
        self.payload_key = payload_key

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def store_event(self, event: Dict[str, Any]) -> None:
        payload = event
        if self.payload_key:
            payload = {self.payload_key: event}

        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.headers,
        }
        if self.bearer_token:
            request_headers["Authorization"] = f"Bearer {self.bearer_token}"

        request = urllib.request.Request(
            url=self.endpoint_url,
            data=body,
            headers=request_headers,
            method=self.method,
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                status = getattr(response, "status", None) or response.getcode()
                if status < 200 or status >= 300:
                    raise RuntimeError(f"REST API adapter received non-success status: {status}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"REST API adapter failed to send event: {exc}") from exc
