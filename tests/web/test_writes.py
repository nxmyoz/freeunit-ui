"""Tests for the mutating endpoints and the rails around them."""

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
from freeunit_ui.settings import ConfigurationError, Settings
from freeunit_ui.unit import UnitWriteClient
from freeunit_ui.web.writes import baseline_digest
from tests.conftest import CONFIG_PAYLOAD, DEFAULT_ROUTES

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


def _token(client: FlaskClient, url: str = "/edit/") -> str:
    """Load a form and extract its CSRF token."""
    body = client.get(url).get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    start = body.index(marker) + len(marker)
    return body[start : body.index('"', start)]


# --- gating ---------------------------------------------------------------


@pytest.mark.parametrize("path", ["/edit/", "/snapshots"])
def test_write_routes_do_not_exist_when_disabled(web: FlaskClient, path: str) -> None:
    # Not "forbidden": the routes are never registered, so there is nothing to reach.
    assert web.get(path).status_code == 404


def test_apply_route_absent_when_disabled(web: FlaskClient) -> None:
    assert web.post("/edit/").status_code == 404


def test_enabling_writes_without_a_secret_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="SECRET_KEY"):
        Settings(enable_writes=True)


def test_short_secret_is_refused() -> None:
    with pytest.raises(ConfigurationError):
        Settings(enable_writes=True, secret_key="tooshort")


def test_navigation_only_offers_editing_when_enabled(web: FlaskClient, writer: FlaskClient) -> None:
    assert "Snapshots" not in web.get("/").get_data(as_text=True)
    assert "Snapshots" in writer.get("/").get_data(as_text=True)


# --- CSRF -----------------------------------------------------------------


def test_apply_without_a_token_is_rejected(writer: FlaskClient, recorder: Recorder) -> None:
    response = writer.post("/edit/", data={"document": "{}", "baseline": "x"})
    assert response.status_code == 400
    assert recorder.writes == []


def test_apply_with_a_wrong_token_is_rejected(writer: FlaskClient, recorder: Recorder) -> None:
    _token(writer)
    response = writer.post(
        "/edit/", data={"csrf_token": "forged", "document": "{}", "baseline": "x"}
    )
    assert response.status_code == 400
    assert recorder.writes == []


def test_restore_requires_a_token(writer: FlaskClient, recorder: Recorder) -> None:
    assert writer.post("/snapshots/whatever/restore").status_code == 400
    assert recorder.writes == []


# --- applying -------------------------------------------------------------


def test_apply_writes_and_snapshots_first(
    writer: FlaskClient, recorder: Recorder, write_app: Flask
) -> None:
    token = _token(writer, "/edit/listeners")
    new = {"*:9090": {"pass": "applications/blog"}}
    response = writer.post(
        "/edit/listeners",
        data={
            "csrf_token": token,
            "baseline": baseline_digest(CONFIG_PAYLOAD["listeners"]),
            "document": json.dumps(new),
        },
    )
    assert response.status_code == 302
    assert recorder.writes == [("PUT", "/config/listeners", new)]

    store = write_app.extensions["freeunit_ui.snapshots"]
    snapshots = store.list()
    assert len(snapshots) == 1
    # The snapshot holds the configuration as it was *before* the change.
    assert snapshots[0].load() == CONFIG_PAYLOAD


def test_invalid_json_is_rejected_before_anything_is_written(
    writer: FlaskClient, recorder: Recorder
) -> None:
    token = _token(writer)
    response = writer.post(
        "/edit/",
        data={"csrf_token": token, "baseline": "x", "document": "{ not json"},
    )
    assert response.status_code == 400
    assert "not valid JSON" in response.get_data(as_text=True)
    assert recorder.writes == []


def test_stale_baseline_is_a_conflict(writer: FlaskClient, recorder: Recorder) -> None:
    token = _token(writer)
    response = writer.post(
        "/edit/",
        data={"csrf_token": token, "baseline": "stale", "document": "{}"},
    )
    assert response.status_code == 409
    assert "changed while you were editing" in response.get_data(as_text=True)
    assert recorder.writes == []


def test_baseline_ignores_key_order(writer: FlaskClient) -> None:
    assert baseline_digest({"a": 1, "b": 2}) == baseline_digest({"b": 2, "a": 1})


def test_api_rejection_surfaces_the_json_pointer(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(
                400,
                json={
                    "detail": "Unknown parameter.",
                    "location": {"path": "/listeners/*:8080"},
                    "suggestion": "pass",
                },
            )
        return httpx.Response(200, json=DEFAULT_ROUTES.get(request.url.path, {}))

    app = create_app(
        Settings(
            enable_writes=True,
            secret_key=SECRET,
            snapshot_dir=tmp_path / "s",
            session_cookie_secure=False,
        ),
        client_factory=lambda: UnitWriteClient(
            httpx.Client(transport=httpx.MockTransport(handler), base_url="http://u")
        ),
        write_client_factory=lambda: UnitWriteClient(
            httpx.Client(transport=httpx.MockTransport(handler), base_url="http://u")
        ),
    )
    with app.test_client() as client:
        token = _token(client)
        response = client.post(
            "/edit/",
            data={
                "csrf_token": token,
                "baseline": baseline_digest(CONFIG_PAYLOAD),
                "document": "{}",
            },
        )
    text = response.get_data(as_text=True)
    assert "/listeners/*:8080" in text
    assert "pass" in text


# --- snapshots ------------------------------------------------------------


def test_restore_replaces_the_whole_configuration(
    writer: FlaskClient, recorder: Recorder, write_app: Flask
) -> None:
    store = write_app.extensions["freeunit_ui.snapshots"]
    saved = store.save({"listeners": {}})

    token = _token(writer, "/snapshots")
    response = writer.post(f"/snapshots/{saved.name}/restore", data={"csrf_token": token})
    assert response.status_code == 302
    assert recorder.writes == [("PUT", "/config", {"listeners": {}})]
    # Restoring is itself undoable: the pre-restore state was snapshotted.
    assert len(store.list()) == 2


def test_snapshots_page_lists_them(writer: FlaskClient, write_app: Flask) -> None:
    write_app.extensions["freeunit_ui.snapshots"].save({"a": 1})
    assert "Restore" in writer.get("/snapshots").get_data(as_text=True)


def test_session_cookie_is_hardened(write_app: Flask) -> None:
    assert write_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert write_app.config["SESSION_COOKIE_SAMESITE"] == "Strict"


# --- configuration guidance ------------------------------------------------


def test_browsing_shows_what_the_members_mean(web: FlaskClient) -> None:
    body = web.get("/config/applications/blog").get_data(as_text=True)
    assert "What this is" in body
    assert "module" in body
    assert "required" in body


def test_guidance_follows_the_application_type(web: FlaskClient) -> None:
    body = web.get("/config/applications/blog").get_data(as_text=True)
    # the python branch, not php or ruby
    assert "module name" in body
    assert "Document root" not in body


def test_editing_an_absent_member_offers_scaffolds(writer: FlaskClient) -> None:
    body = writer.get("/edit/applications/brand-new").get_data(as_text=True)
    assert "Nothing is configured at this path yet" in body
    assert "Python application" in body


def test_a_scaffold_prefills_the_editor(writer: FlaskClient) -> None:
    body = writer.get("/edit/applications/brand-new?template=python-application").get_data(
        as_text=True
    )
    assert "&#34;module&#34;" in body
    assert "&#34;callable&#34;" in body


def test_an_unknown_template_is_ignored(writer: FlaskClient) -> None:
    assert writer.get("/edit/applications/x?template=nope").status_code == 200


def test_creating_an_absent_member_applies(writer: FlaskClient, recorder: Recorder) -> None:
    from freeunit_ui.web.writes import baseline_digest

    token = _token(writer, "/edit/applications/brand-new")
    response = writer.post(
        "/edit/applications/brand-new",
        data={
            "csrf_token": token,
            # nothing is there yet, so the baseline is the digest of absence
            "baseline": baseline_digest(None),
            "document": '{"type": "python 3", "module": "new.wsgi"}',
        },
    )
    assert response.status_code == 302
    assert recorder.writes == [
        ("PUT", "/config/applications/brand-new", {"type": "python 3", "module": "new.wsgi"})
    ]
