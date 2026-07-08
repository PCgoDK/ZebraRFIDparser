from __future__ import annotations

import json
from typing import Any

from rest_api_adapter import RESTAPIAdapter


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def getcode(self) -> int:
        return self.status


class _FakeUrlOpen:
    def __init__(self) -> None:
        self.last_request = None
        self.last_timeout = None

    def __call__(self, request: Any, timeout: float) -> _FakeResponse:
        self.last_request = request
        self.last_timeout = timeout
        return _FakeResponse(status=201)


def test_rest_api_adapter_posts_json(monkeypatch: Any) -> None:
    fake = _FakeUrlOpen()
    monkeypatch.setattr("urllib.request.urlopen", fake)

    adapter = RESTAPIAdapter(
        endpoint_url="https://example.local/events",
        timeout_seconds=3.5,
        method="POST",
        headers={"X-Test": "yes"},
        bearer_token="token123",
        payload_key="event",
    )

    event = {"tag_id": "ABC123", "reader_id": "R1"}
    adapter.store_event(event)

    assert fake.last_request is not None
    assert fake.last_timeout == 3.5
    assert fake.last_request.get_method() == "POST"
    assert fake.last_request.headers["Content-type"] == "application/json"
    assert fake.last_request.headers["X-test"] == "yes"
    assert fake.last_request.headers["Authorization"] == "Bearer token123"

    body = json.loads(fake.last_request.data.decode("utf-8"))
    assert body == {"event": event}


def test_rest_api_adapter_requires_endpoint() -> None:
    try:
        RESTAPIAdapter(endpoint_url="")
        assert False, "Expected ValueError when endpoint_url is empty"
    except ValueError as exc:
        assert "endpoint_url" in str(exc)
