"""End-to-end tests of the rendered interface."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from flask import Flask
from flask.testing import FlaskClient

from freeunit_ui.app import create_app
from freeunit_ui.settings import Settings
from tests.conftest import make_client, make_handler


def test_dashboard_renders_counters(web: FlaskClient) -> None:
    response = web.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Overview" in body
    assert "blog" in body
    assert "41" in body


def test_dashboard_shows_telemetry_when_present(web: FlaskClient) -> None:
    assert "Spans exported" in web.get("/").get_data(as_text=True)


def test_dashboard_hides_telemetry_when_absent(routes: dict[str, Any]) -> None:
    routes["/status"] = {"connections": {"active": 0}}
    app = create_app(Settings(), client_factory=lambda: make_client(make_handler(routes)))
    with app.test_client() as client:
        assert "Spans exported" not in client.get("/").get_data(as_text=True)


def test_expiring_certificate_is_highlighted(routes: dict[str, Any]) -> None:
    routes["/certificates"] = {
        "soon": {"chain": [{"validity": {"until": "Jan  1 00:00:00 2020 GMT"}}]}
    }
    app = create_app(Settings(), client_factory=lambda: make_client(make_handler(routes)))
    with app.test_client() as client:
        body = client.get("/").get_data(as_text=True)
    assert "Expired" in body


def test_config_root_lists_members(web: FlaskClient) -> None:
    body = web.get("/config").get_data(as_text=True)
    assert "listeners" in body
    assert "applications" in body


def test_config_subpath_is_fetched(web: FlaskClient) -> None:
    body = web.get("/config/listeners").get_data(as_text=True)
    assert "*:8080" in body


def test_config_rejects_relative_path(web: FlaskClient) -> None:
    response = web.get("/config/a/../b")
    assert response.status_code == 400
    assert "Invalid path" in response.get_data(as_text=True)


def test_missing_config_member_renders_404(web: FlaskClient) -> None:
    response = web.get("/config/nope")
    assert response.status_code == 404


def test_certificates_page_lists_bundles(web: FlaskClient) -> None:
    body = web.get("/certificates").get_data(as_text=True)
    assert "example.com" in body
    assert "www.example.com" in body


def test_unreachable_control_socket_renders_502() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    app = create_app(Settings(), client_factory=lambda: make_client(explode))
    with app.test_client() as client:
        response = client.get("/")
    assert response.status_code == 502
    assert "unreachable" in response.get_data(as_text=True)


def test_api_error_page_shows_pointer_and_suggestion() -> None:
    body = {"detail": "Unknown parameter.", "location": {"path": "/a"}, "suggestion": "pass"}
    app = create_app(
        Settings(),
        client_factory=lambda: make_client(make_handler(error_body=body, status_code=400)),
    )
    with app.test_client() as client:
        response = client.get("/config")
    assert response.status_code == 502
    text = response.get_data(as_text=True)
    assert "/a" in text
    assert "pass" in text


@pytest.mark.parametrize("path", ["/", "/config", "/certificates"])
def test_security_headers_present(web: FlaskClient, path: str) -> None:
    headers = web.get(path).headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert "script-src" not in headers["Content-Security-Policy"]


def test_pages_contain_no_javascript(web: FlaskClient) -> None:
    for path in ("/", "/config", "/certificates"):
        body = web.get(path).get_data(as_text=True)
        assert "<script" not in body.lower()
        assert "onclick" not in body.lower()


def test_app_uses_default_factory_when_none_given() -> None:
    app = create_app(Settings(control="/definitely/missing.sock"))
    assert isinstance(app, Flask)
    with app.test_client() as client:
        assert client.get("/").status_code == 502


def test_hostile_configuration_values_cannot_inject_markup(routes: dict[str, Any]) -> None:
    # Configuration content is attacker-influenced in the sense that whoever can
    # write config chooses these strings; the interface must never render them raw.
    routes["/config"] = {
        "listeners": {
            "<img src=x onerror=alert(1)>": {"pass": "</code></pre><script>alert(2)</script>"}
        }
    }
    app = create_app(Settings(), client_factory=lambda: make_client(make_handler(routes)))
    with app.test_client() as client:
        body = client.get("/config").get_data(as_text=True)

    assert "<script>alert(2)</script>" not in body
    assert "onerror=alert(1)>" not in body
    assert "&lt;script&gt;" in body


def test_healthz_does_not_touch_the_control_socket() -> None:
    # A unitd outage must not remove this interface from a proxy's pool.
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    app = create_app(Settings(), client_factory=lambda: make_client(explode))
    with app.test_client() as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "ok\n"


def test_oversized_document_is_truncated(routes: dict[str, Any]) -> None:
    routes["/config"] = {"blob": "x" * 5000}
    app = create_app(
        Settings(max_render_chars=1000), client_factory=lambda: make_client(make_handler(routes))
    )
    with app.test_client() as client:
        body = client.get("/config").get_data(as_text=True)
    assert "truncated" in body
