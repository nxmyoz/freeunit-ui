"""Fixtures shared by the write-side tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from flask import Flask
from flask.testing import FlaskClient

from freeunit_ui.app import create_app
from freeunit_ui.settings import Settings
from freeunit_ui.unit import UnitWriteClient
from tests.conftest import DEFAULT_ROUTES

SECRET = "k" * 40


class Recorder:
    """Mock control API that records mutating requests."""

    def __init__(self, routes: dict[str, Any]) -> None:
        """Start with a copy of the canned routes."""
        self.routes = dict(routes)
        self.writes: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method in {"PUT", "DELETE"}:
            body = json.loads(request.content) if request.content else None
            self.writes.append((request.method, path, body))
            if body is not None:
                self.routes[path] = body
            return httpx.Response(200, json={"success": "Reconfiguration done."})
        if path in self.routes:
            return httpx.Response(200, json=self.routes[path])
        return httpx.Response(404, json={"error": "Value doesn't exist."})


@pytest.fixture
def recorder() -> Recorder:
    return Recorder(DEFAULT_ROUTES)


@pytest.fixture
def write_app(recorder: Recorder, tmp_path: Path) -> Flask:
    def factory() -> UnitWriteClient:
        return UnitWriteClient(
            httpx.Client(transport=httpx.MockTransport(recorder), base_url="http://unit")
        )

    return create_app(
        Settings(
            enable_writes=True,
            secret_key=SECRET,
            snapshot_dir=tmp_path / "snaps",
            session_cookie_secure=False,
        ),
        client_factory=factory,
        write_client_factory=factory,
    )


@pytest.fixture
def writer(write_app: Flask) -> Iterator[FlaskClient]:
    with write_app.test_client() as client:
        yield client
