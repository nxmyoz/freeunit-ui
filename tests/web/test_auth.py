"""Tests for the proxy-asserted identity gate."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from flask import Flask
from flask.testing import FlaskClient

from freeunit_ui.app import create_app
from freeunit_ui.settings import ConfigurationError, Settings
from freeunit_ui.unit import UnitWriteClient
from tests.conftest import DEFAULT_ROUTES, make_client, make_handler
from tests.web.conftest import token_from

HEADER = "X-Forwarded-User"


def _app(**kwargs: object) -> Flask:
    return create_app(
        Settings(**kwargs),  # type: ignore[arg-type]
        client_factory=lambda: make_client(make_handler(DEFAULT_ROUTES)),
    )


def test_require_auth_without_a_header_name_is_refused() -> None:
    # A gate that names no header cannot be enforced, so it fails at startup.
    with pytest.raises(ConfigurationError, match="AUTH_HEADER"):
        Settings(require_auth=True)


def test_identity_is_ignored_unless_a_header_is_configured() -> None:
    app = _app()
    with app.test_client() as client:
        body = client.get("/", headers={HEADER: "someone"}).get_data(as_text=True)
    assert "someone" not in body


def test_identity_is_shown_when_configured() -> None:
    app = _app(auth_header=HEADER)
    with app.test_client() as client:
        body = client.get("/", headers={HEADER: "alice@example.com"}).get_data(as_text=True)
    assert "alice@example.com" in body


def test_unauthenticated_requests_are_refused_when_required() -> None:
    app = _app(auth_header=HEADER, require_auth=True)
    with app.test_client() as client:
        assert client.get("/").status_code == 401
        assert client.get("/config").status_code == 401
        assert client.get("/", headers={HEADER: "alice"}).status_code == 200


def test_blank_identity_does_not_pass_the_gate() -> None:
    app = _app(auth_header=HEADER, require_auth=True)
    with app.test_client() as client:
        assert client.get("/", headers={HEADER: "   "}).status_code == 401


def test_healthz_stays_reachable_for_the_proxy() -> None:
    # The proxy probes liveness before it can authenticate anyone.
    app = _app(auth_header=HEADER, require_auth=True)
    with app.test_client() as client:
        assert client.get("/healthz").status_code == 200


def test_snapshots_record_who_made_the_change(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, json={"success": "done"})
        return httpx.Response(200, json=DEFAULT_ROUTES.get(request.url.path, {}))

    def factory() -> UnitWriteClient:
        return UnitWriteClient(
            httpx.Client(transport=httpx.MockTransport(handler), base_url="http://u")
        )

    app = create_app(
        Settings(
            auth_header=HEADER,
            require_auth=True,
            enable_writes=True,
            secret_key="k" * 40,
            snapshot_dir=tmp_path / "s",
            session_cookie_secure=False,
        ),
        client_factory=factory,
        write_client_factory=factory,
    )
    headers = {HEADER: "alice@example.com"}
    client: FlaskClient
    with app.test_client() as client:
        token = token_from(client, "/edit/", headers=headers)
        baseline_page = client.get("/config", headers=headers)
        assert baseline_page.status_code == 200

        from freeunit_ui.web.writes import baseline_digest
        from tests.conftest import CONFIG_PAYLOAD

        response = client.post(
            "/edit/",
            headers=headers,
            data={
                "csrf_token": token,
                "baseline": baseline_digest(CONFIG_PAYLOAD),
                "document": "{}",
            },
        )
        assert response.status_code == 302

        listing = client.get("/snapshots", headers=headers).get_data(as_text=True)

    store = app.extensions["freeunit_ui.snapshots"]
    assert [snap.author for snap in store.list()] == ["alice@example.com"]
    assert "alice@example.com" in listing


def test_snapshot_file_is_a_plain_config_document(tmp_path: Path) -> None:
    # It must stay usable with curl or unitctl without unwrapping.
    from freeunit_ui.snapshots import SnapshotStore

    store = SnapshotStore(tmp_path)
    snapshot = store.save({"listeners": {}}, author="alice")
    assert snapshot.path.read_text().lstrip().startswith("{")
    assert snapshot.load() == {"listeners": {}}
    assert store.list()[0].author == "alice"
