"""Shared fixtures and canned control API payloads."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from flask import Flask
from flask.testing import FlaskClient

from freeunit_ui.app import create_app
from freeunit_ui.settings import Settings
from freeunit_ui.unit import UnitClient

STATUS_PAYLOAD: dict[str, Any] = {
    "connections": {"accepted": 12, "active": 2, "idle": 3, "closed": 7},
    "requests": {"total": 41},
    "applications": {
        "blog": {
            "processes": {"running": 2, "starting": 0, "idle": 1},
            "requests": {"active": 1},
        }
    },
    "telemetry": {"spans": {"exported": 90, "failed": 2}},
}

CONFIG_PAYLOAD: dict[str, Any] = {
    "listeners": {"*:8080": {"pass": "applications/blog"}},
    "applications": {"blog": {"type": "python 3", "path": "/srv/blog"}},
}

CERTIFICATES_PAYLOAD: dict[str, Any] = {
    "example": {
        "key": "RSA (2048 bits)",
        "chain": [
            {
                "subject": {"common_name": "example.com", "alt_names": ["www.example.com"]},
                "issuer": {"common_name": "Test CA"},
                "validity": {
                    "since": "Jan  1 00:00:00 2026 GMT",
                    "until": "Jan  1 00:00:00 2099 GMT",
                },
            }
        ],
    }
}


def make_handler(
    routes: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    error_body: Any = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a MockTransport handler serving ``routes`` by path."""
    table = routes if routes is not None else {}

    def handler(request: httpx.Request) -> httpx.Response:
        if error_body is not None:
            return httpx.Response(status_code, json=error_body)
        if request.url.path in table:
            return httpx.Response(200, json=table[request.url.path])
        return httpx.Response(404, json={"error": "Value doesn't exist."})

    return handler


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> UnitClient:
    """Build a UnitClient backed by a mock transport."""
    return UnitClient(httpx.Client(transport=httpx.MockTransport(handler), base_url="http://unit"))


DEFAULT_ROUTES: dict[str, Any] = {
    "/status": STATUS_PAYLOAD,
    "/config": CONFIG_PAYLOAD,
    "/config/listeners": CONFIG_PAYLOAD["listeners"],
    "/certificates": CERTIFICATES_PAYLOAD,
}


@pytest.fixture
def routes() -> dict[str, Any]:
    """Mutable copy of the default routing table for a test."""
    return dict(DEFAULT_ROUTES)


@pytest.fixture
def app(routes: dict[str, Any]) -> Flask:
    """Application wired to a mock control API."""
    return create_app(
        Settings(control="/nonexistent.sock"),
        client_factory=lambda: make_client(make_handler(routes)),
    )


@pytest.fixture
def web(app: Flask) -> Iterator[FlaskClient]:
    """Flask test client."""
    with app.test_client() as client:
        yield client
