"""End-to-end test over a real UNIX domain socket.

Everything else drives the client through ``httpx.MockTransport``, which never
touches a socket. This exercises the transport actually used against unitd.
"""

from __future__ import annotations

import json
import socketserver
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from freeunit_ui.app import create_app
from freeunit_ui.settings import Settings
from freeunit_ui.unit import UnitClient
from tests.conftest import DEFAULT_ROUTES


class _Handler(BaseHTTPRequestHandler):
    """Serve the canned control API payloads."""

    protocol_version = "HTTP/1.1"

    # Name is fixed by BaseHTTPRequestHandler.
    def do_GET(self) -> None:
        payload = DEFAULT_ROUTES.get(self.path)
        status = 200 if payload is not None else 404
        body = json.dumps(payload if payload is not None else {"error": "nope"}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence the default stderr logging."""


class _UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True


@pytest.fixture
def unit_socket(tmp_path: Path) -> Iterator[str]:
    """Run a fake unitd on a UNIX socket and yield its path."""
    path = str(tmp_path / "control.sock")
    server = _UnixHTTPServer(path, _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_client_talks_over_a_unix_socket(unit_socket: str) -> None:
    with UnitClient.connect(unit_socket) as client:
        status = client.get_status()
    assert status.connections.active == 2


def test_application_renders_against_a_unix_socket(unit_socket: str) -> None:
    app = create_app(Settings(control=unit_socket))
    client: FlaskClient
    with app.test_client() as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "blog" in response.get_data(as_text=True)
