"""Tests for the mutating endpoints and the rails around them."""

from __future__ import annotations

import json
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
from tests.web.conftest import SECRET, Recorder, token_from

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
    token_from(writer, "/edit/")
    response = writer.post(
        "/edit/", data={"csrf_token": "forged", "document": "{}", "baseline": "x"}
    )
    assert response.status_code == 400
    assert recorder.writes == []


def test_restore_requires_a_token(writer: FlaskClient, recorder: Recorder) -> None:
    assert writer.post("/snapshots/whatever/restore").status_code == 400
    assert recorder.writes == []


def test_a_non_ascii_token_is_a_mismatch_not_a_crash(
    writer: FlaskClient, recorder: Recorder
) -> None:
    # hmac.compare_digest raises TypeError on a str argument outside ASCII,
    # and the submitted token is attacker-controlled - it must come back as
    # the usual 400 rejection, not a 500.
    token_from(writer, "/edit/")
    response = writer.post(
        "/edit/", data={"csrf_token": "föörged", "document": "{}", "baseline": "x"}
    )
    assert response.status_code == 400
    assert recorder.writes == []


# --- applying -------------------------------------------------------------


def test_apply_writes_and_snapshots_first(
    writer: FlaskClient, recorder: Recorder, write_app: Flask
) -> None:
    token = token_from(writer, "/edit/listeners")
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


def test_a_document_between_500kb_and_the_upload_limit_is_accepted(
    writer: FlaskClient, recorder: Recorder
) -> None:
    # Werkzeug caps non-file form fields at 500 KB by default, independent of
    # MAX_CONTENT_LENGTH. A document submitted through this plain <textarea>
    # form must be bound by max_upload_bytes (1 MiB by default here), the
    # limit this interface actually documents, not Werkzeug's own default.
    token = token_from(writer, "/edit/listeners")
    padded = {"*:9090": {"pass": "applications/blog"}, "padding": "x" * 600_000}
    response = writer.post(
        "/edit/listeners",
        data={
            "csrf_token": token,
            "baseline": baseline_digest(CONFIG_PAYLOAD["listeners"]),
            "document": json.dumps(padded),
        },
    )
    assert response.status_code == 302
    assert recorder.writes == [("PUT", "/config/listeners", padded)]


def test_invalid_json_is_rejected_before_anything_is_written(
    writer: FlaskClient, recorder: Recorder
) -> None:
    token = token_from(writer, "/edit/")
    response = writer.post(
        "/edit/",
        data={"csrf_token": token, "baseline": "x", "document": "{ not json"},
    )
    assert response.status_code == 400
    assert "not valid JSON" in response.get_data(as_text=True)
    assert recorder.writes == []


def test_stale_baseline_is_a_conflict(writer: FlaskClient, recorder: Recorder) -> None:
    token = token_from(writer, "/edit/")
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
        token = token_from(client, "/edit/")
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


def test_a_snapshot_storage_failure_is_a_500_not_a_404(tmp_path: Path) -> None:
    # SnapshotStore.save() and SnapshotNotFoundError.get() used to share one
    # exception type, so a disk-full or permission failure while writing a
    # snapshot was reported the same way as "that snapshot name does not
    # exist" - a 404 that hides a real storage problem behind a wrong error.
    blocker = tmp_path / "blocked"
    blocker.write_text("occupying the path the snapshot directory needs")

    app = create_app(
        Settings(
            enable_writes=True,
            secret_key=SECRET,
            snapshot_dir=blocker / "snaps",
            session_cookie_secure=False,
        ),
        client_factory=lambda: UnitWriteClient(
            httpx.Client(
                transport=httpx.MockTransport(Recorder(DEFAULT_ROUTES)), base_url="http://u"
            )
        ),
        write_client_factory=lambda: UnitWriteClient(
            httpx.Client(
                transport=httpx.MockTransport(Recorder(DEFAULT_ROUTES)), base_url="http://u"
            )
        ),
    )
    with app.test_client() as client:
        token = token_from(client, "/edit/")
        response = client.post(
            "/edit/",
            data={
                "csrf_token": token,
                "baseline": baseline_digest(CONFIG_PAYLOAD),
                "document": "{}",
            },
        )
    assert response.status_code == 500


# --- snapshots ------------------------------------------------------------


def test_restore_replaces_the_whole_configuration(
    writer: FlaskClient, recorder: Recorder, write_app: Flask
) -> None:
    store = write_app.extensions["freeunit_ui.snapshots"]
    saved = store.save({"listeners": {}})

    token = token_from(writer, "/snapshots")
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


def test_the_reference_panel_is_not_inside_the_page_title(writer: FlaskClient) -> None:
    # Regression test: the reference panel ("Members here", the table of
    # what each member means) used to be emitted inside {% block title %},
    # so its whole content - including its own markup - ended up inside
    # <title>...</title> instead of the page body, where a browser would
    # never render it.
    body = writer.get("/edit/applications/blog").get_data(as_text=True)
    title_start = body.index("<title>") + len("<title>")
    title_end = body.index("</title>")
    title = body[title_start:title_end]
    assert "<section" not in title
    assert "Members here" not in title
    assert "Members here" in body[title_end:]


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


def test_an_existing_object_does_not_offer_scaffolds(writer: FlaskClient) -> None:
    # "Start from" is for something that does not exist yet; offering it on
    # an object that already has real content invites clicking it by habit
    # and silently swapping the editor's contents out from under it.
    body = writer.get("/edit/applications/blog").get_data(as_text=True)
    assert "Start from" not in body
    assert "Python application" not in body


def test_a_template_on_an_existing_object_is_ignored(writer: FlaskClient) -> None:
    # Even a hand-crafted ?template= must not be able to swap a real,
    # existing object's editor contents for a fresh scaffold: if applied
    # unnoticed, the baseline still matches and the real object is
    # silently replaced.
    body = writer.get("/edit/applications/blog?template=python-application").get_data(as_text=True)
    assert "/srv/blog" in body
    assert "&#34;callable&#34;" not in body


def test_creating_an_absent_member_applies(writer: FlaskClient, recorder: Recorder) -> None:
    from freeunit_ui.web.writes import baseline_digest

    token = token_from(writer, "/edit/applications/brand-new")
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


# --- advisory checks in the form -------------------------------------------


def test_check_button_reports_without_applying(writer: FlaskClient, recorder: Recorder) -> None:
    token = token_from(writer, "/edit/applications/new")
    response = writer.post(
        "/edit/applications/new",
        data={
            "csrf_token": token,
            "baseline": "irrelevant",
            "document": '{"type": "python 3"}',
            "action": "check",
        },
    )
    assert response.status_code == 200
    assert "is required here" in response.get_data(as_text=True)
    assert recorder.writes == []


def test_apply_with_findings_asks_before_writing(writer: FlaskClient, recorder: Recorder) -> None:
    from freeunit_ui.web.writes import baseline_digest

    token = token_from(writer, "/edit/applications/new")
    response = writer.post(
        "/edit/applications/new",
        data={
            "csrf_token": token,
            "baseline": baseline_digest(None),
            "document": '{"type": "python 3"}',
            "action": "apply",
        },
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "This looks wrong" in body
    assert "Apply anyway" in body
    assert recorder.writes == []


def test_confirming_applies_despite_findings(writer: FlaskClient, recorder: Recorder) -> None:
    # Findings are advisory: the operator can always proceed, because the
    # bundled specification may simply be older than the server.
    from freeunit_ui.web.writes import baseline_digest

    token = token_from(writer, "/edit/applications/new")
    response = writer.post(
        "/edit/applications/new",
        data={
            "csrf_token": token,
            "baseline": baseline_digest(None),
            "document": '{"type": "python 3"}',
            "action": "apply",
            "confirm": "yes",
        },
    )
    assert response.status_code == 302
    assert recorder.writes == [("PUT", "/config/applications/new", {"type": "python 3"})]


def test_a_clean_document_applies_without_confirmation(
    writer: FlaskClient, recorder: Recorder
) -> None:
    from freeunit_ui.web.writes import baseline_digest

    token = token_from(writer, "/edit/applications/new")
    response = writer.post(
        "/edit/applications/new",
        data={
            "csrf_token": token,
            "baseline": baseline_digest(None),
            "document": '{"type": "python 3", "module": "new.wsgi"}',
            "action": "apply",
        },
    )
    assert response.status_code == 302
    assert len(recorder.writes) == 1


# --- change lifecycle ------------------------------------------------------


def _apply(client: FlaskClient, subpath: str, document: str, **extra: str) -> Any:
    """Apply a document, confirming past any advisory findings."""
    from freeunit_ui.web.writes import baseline_digest

    token = token_from(client, f"/edit/{subpath}")
    data = {
        "csrf_token": token,
        "baseline": baseline_digest(None),
        "document": document,
        "action": "apply",
        "confirm": "yes",
        **extra,
    }
    return client.post(f"/edit/{subpath}", data=data)


def test_reason_is_recorded_with_the_snapshot(writer: FlaskClient, write_app: Flask) -> None:
    _apply(
        writer,
        "applications/why",
        '{"type": "python 3", "module": "m"}',
        reason="rotating the blog certificate",
    )
    store = write_app.extensions["freeunit_ui.snapshots"]
    assert store.list()[0].reason == "rotating the blog certificate"


def test_a_blank_reason_is_stored_as_none(writer: FlaskClient, write_app: Flask) -> None:
    _apply(writer, "applications/why", '{"type": "python 3", "module": "m"}', reason="   ")
    assert write_app.extensions["freeunit_ui.snapshots"].list()[0].reason is None


def test_snapshots_page_shows_the_reason(writer: FlaskClient, write_app: Flask) -> None:
    write_app.extensions["freeunit_ui.snapshots"].save({}, author="a", reason="a good reason")
    assert "a good reason" in writer.get("/snapshots").get_data(as_text=True)


def test_applying_redirects_with_an_undo_pointer(writer: FlaskClient) -> None:
    response = _apply(writer, "applications/undoable", '{"type": "python 3", "module": "m"}')
    assert response.status_code == 302
    assert "undo=" in response.headers["Location"]
    assert "outcome=applied" in response.headers["Location"]


def test_the_undo_banner_offers_a_restore(writer: FlaskClient, write_app: Flask) -> None:
    snapshot = write_app.extensions["freeunit_ui.snapshots"].save({"listeners": {}})
    body = writer.get(f"/config?undo={snapshot.name}&outcome=applied").get_data(as_text=True)
    assert "Applied." in body
    assert f"/snapshots/{snapshot.name}/restore" in body


def test_a_bogus_undo_name_shows_no_banner(writer: FlaskClient) -> None:
    body = writer.get("/config?undo=../../etc/passwd&outcome=applied").get_data(as_text=True)
    assert "Applied." not in body


def test_no_undo_banner_when_writes_are_disabled(web: FlaskClient) -> None:
    assert "Applied." not in web.get("/config?undo=anything").get_data(as_text=True)


def test_a_stored_document_differing_from_what_was_sent_is_reported(tmp_path: Path) -> None:
    # unitd accepting a document does not mean it stored it verbatim.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            return httpx.Response(200, json={"success": "done"})
        if request.url.path == "/config/applications/lossy":
            return httpx.Response(200, json={"type": "python 3"})  # module dropped
        return httpx.Response(200, json=DEFAULT_ROUTES.get(request.url.path, {}))

    def factory() -> UnitWriteClient:
        return UnitWriteClient(
            httpx.Client(transport=httpx.MockTransport(handler), base_url="http://u")
        )

    app = create_app(
        Settings(
            enable_writes=True,
            secret_key=SECRET,
            snapshot_dir=tmp_path / "s",
            session_cookie_secure=False,
        ),
        client_factory=factory,
        write_client_factory=factory,
    )
    with app.test_client() as client:
        from freeunit_ui.web.writes import baseline_digest

        token = token_from(client, "/edit/applications/lossy")
        response = client.post(
            "/edit/applications/lossy",
            data={
                "csrf_token": token,
                "baseline": baseline_digest({"type": "python 3"}),
                "document": '{"type": "python 3", "module": "m"}',
                "action": "apply",
                "confirm": "yes",
            },
        )
        assert "outcome=differs" in response.headers["Location"]
        body = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "differs from what you sent" in body


def test_restoring_records_why(writer: FlaskClient, write_app: Flask) -> None:
    store = write_app.extensions["freeunit_ui.snapshots"]
    saved = store.save({"listeners": {}})
    token = token_from(writer, "/snapshots")
    writer.post(f"/snapshots/{saved.name}/restore", data={"csrf_token": token})
    assert store.list()[0].reason == f"before restoring snapshot {saved.name}"


# --- diff ------------------------------------------------------------------


def test_diff_against_the_running_configuration(writer: FlaskClient, write_app: Flask) -> None:
    store = write_app.extensions["freeunit_ui.snapshots"]
    saved = store.save({"listeners": {"*:80": {"pass": "routes/old"}}})
    body = writer.get(f"/snapshots/{saved.name}/diff").get_data(as_text=True)
    assert "running configuration" in body
    assert "/listeners" in body


def test_diff_between_two_snapshots(writer: FlaskClient, write_app: Flask) -> None:
    store = write_app.extensions["freeunit_ui.snapshots"]
    first = store.save({"settings": {"http": {"idle_timeout": 180}}})
    second = store.save({"settings": {"http": {"idle_timeout": 30}}})
    body = writer.get(f"/snapshots/{first.name}/diff?against={second.name}").get_data(as_text=True)
    assert "/settings/http/idle_timeout" in body
    assert "180" in body
    assert "30" in body


def test_diff_of_an_unchanged_snapshot_says_so(writer: FlaskClient, write_app: Flask) -> None:
    from tests.conftest import CONFIG_PAYLOAD

    store = write_app.extensions["freeunit_ui.snapshots"]
    saved = store.save(CONFIG_PAYLOAD)
    body = writer.get(f"/snapshots/{saved.name}/diff").get_data(as_text=True)
    assert "No differences" in body


def test_diff_of_a_missing_snapshot_is_a_404(writer: FlaskClient) -> None:
    assert writer.get("/snapshots/nope/diff").status_code == 404


def test_snapshots_page_links_to_the_diff(writer: FlaskClient, write_app: Flask) -> None:
    saved = write_app.extensions["freeunit_ui.snapshots"].save({})
    body = writer.get("/snapshots").get_data(as_text=True)
    assert f"/snapshots/{saved.name}/diff" in body
