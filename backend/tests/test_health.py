import asyncio
import json
from collections.abc import Mapping
from typing import Any

from starlette.types import Message, Scope

from app.main import app

AsgiResponse = tuple[int, dict[str, str], dict[str, Any]]


async def _asgi_get(
    path: str,
    headers: Mapping[str, str] | None = None,
) -> AsgiResponse:
    encoded_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": encoded_headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    body_parts: list[bytes] = []
    status_code = 500
    response_headers: dict[str, str] = {}
    request_sent = False

    async def receive() -> Message:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        nonlocal status_code, response_headers
        if message["type"] == "http.response.start":
            status_code = message["status"]
            response_headers = {
                key.decode("latin-1"): value.decode("latin-1")
                for key, value in message["headers"]
            }
        if message["type"] == "http.response.body":
            body_parts.append(message.get("body", b""))

    await app(scope, receive, send)
    body = json.loads(b"".join(body_parts).decode("utf-8"))
    return status_code, response_headers, body


def get(path: str, headers: Mapping[str, str] | None = None) -> AsgiResponse:
    return asyncio.run(_asgi_get(path, headers))


def test_health_endpoint_returns_http_200() -> None:
    status_code, _, _ = get("/api/v1/health")

    assert status_code == 200


def test_health_response_schema_is_correct() -> None:
    _, _, body = get("/api/v1/health")

    assert body == {
        "status": "healthy",
        "service": "familykart-api",
        "version": "0.1.0",
    }


def test_request_id_header_is_returned() -> None:
    _, headers, _ = get("/api/v1/health", {"X-Request-ID": "test-id"})

    assert headers["x-request-id"] == "test-id"


def test_unknown_routes_return_standardized_errors() -> None:
    status_code, _, body = get("/missing")

    assert status_code == 404
    assert body["error"]["code"] == "http_404"
    assert body["error"]["message"] == "Not Found"
    assert "request_id" in body["error"]
