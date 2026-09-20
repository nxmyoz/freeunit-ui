"""Tests for operations that are not configuration changes."""

from __future__ import annotations

import io
from typing import Any

from flask.testing import FlaskClient

from tests.web.conftest import Recorder, token_from

# --- restart ---------------------------------------------------------------


def test_restart_is_offered_only_when_writes_are_enabled(
    web: FlaskClient, writer: FlaskClient
) -> None:
    assert "Restart" not in web.get("/").get_data(as_text=True)
    assert "Restart" in writer.get("/").get_data(as_text=True)


def test_restarting_calls_the_control_endpoint(writer: FlaskClient, recorder: Recorder) -> None:
    token = token_from(writer, "/")
    response = writer.post("/applications/blog/restart", data={"csrf_token": token})
    assert response.status_code == 302
    assert recorder.writes == [("GET", "/control/applications/blog/restart", None)]


def test_restart_takes_no_snapshot(writer: FlaskClient, write_app: Any, recorder: Recorder) -> None:
    # Restarting stores nothing, so there is nothing to roll back to.
    token = token_from(writer, "/")
    writer.post("/applications/blog/restart", data={"csrf_token": token})
    assert write_app.extensions["freeunit_ui.snapshots"].list() == []


def test_restart_requires_a_token(writer: FlaskClient, recorder: Recorder) -> None:
    # Unit exposes restart as a GET, which would otherwise be triggerable from
    # any page an operator visits.
    assert writer.post("/applications/blog/restart").status_code == 400
    assert recorder.writes == []


def test_restart_route_absent_without_writes(web: FlaskClient) -> None:
    assert web.post("/applications/blog/restart").status_code == 404


def test_the_overview_confirms_a_restart(writer: FlaskClient) -> None:
    assert "Restarted" in writer.get("/?restarted=blog").get_data(as_text=True)


# --- certificate upload ----------------------------------------------------


def test_uploading_a_bundle_stores_it(writer: FlaskClient, recorder: Recorder) -> None:
    token = token_from(writer, "/certificates/upload")
    pem = b"-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n"
    response = writer.post(
        "/certificates/upload",
        data={
            "csrf_token": token,
            "name": "example-org",
            "bundle": (io.BytesIO(pem), "fullchain.pem"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    method, path, _ = recorder.writes[0]
    assert (method, path) == ("PUT", "/certificates/example-org")


def test_a_pasted_bundle_works_too(writer: FlaskClient, recorder: Recorder) -> None:
    token = token_from(writer, "/certificates/upload")
    response = writer.post(
        "/certificates/upload",
        data={
            "csrf_token": token,
            "name": "pasted",
            "pasted": "-----BEGIN CERTIFICATE-----\nabc\n",
        },
    )
    assert response.status_code == 302
    assert recorder.writes[0][1] == "/certificates/pasted"


def test_a_bundle_that_is_not_pem_is_refused(writer: FlaskClient, recorder: Recorder) -> None:
    token = token_from(writer, "/certificates/upload")
    response = writer.post(
        "/certificates/upload",
        data={"csrf_token": token, "name": "junk", "pasted": "this is not a certificate"},
    )
    assert response.status_code == 400
    assert "does not look like PEM" in response.get_data(as_text=True)
    assert recorder.writes == []


def test_a_name_with_a_slash_is_refused(writer: FlaskClient, recorder: Recorder) -> None:
    token = token_from(writer, "/certificates/upload")
    response = writer.post(
        "/certificates/upload",
        data={"csrf_token": token, "name": "../escape", "pasted": "-----BEGIN X-----"},
    )
    assert response.status_code == 400
    assert recorder.writes == []


def test_key_material_is_never_echoed_back(writer: FlaskClient) -> None:
    # A failed upload must not redisplay the private key in a page.
    token = token_from(writer, "/certificates/upload")
    secret = "-----BEGIN PRIVATE KEY-----\nSUPERSECRETKEYMATERIAL\n"
    response = writer.post(
        "/certificates/upload",
        data={"csrf_token": token, "name": "", "pasted": secret},
    )
    assert response.status_code == 400
    assert "SUPERSECRETKEYMATERIAL" not in response.get_data(as_text=True)


def test_upload_takes_no_snapshot(writer: FlaskClient, write_app: Any) -> None:
    # Snapshots are world-readable to root and kept on disk; a private key
    # must never end up in one.
    token = token_from(writer, "/certificates/upload")
    writer.post(
        "/certificates/upload",
        data={"csrf_token": token, "name": "k", "pasted": "-----BEGIN PRIVATE KEY-----\nx"},
    )
    assert write_app.extensions["freeunit_ui.snapshots"].list() == []


def test_upload_requires_a_token(writer: FlaskClient, recorder: Recorder) -> None:
    assert writer.post("/certificates/upload", data={"name": "x"}).status_code == 400
    assert recorder.writes == []


def test_upload_route_absent_without_writes(web: FlaskClient) -> None:
    assert web.get("/certificates/upload").status_code == 404


def test_certificates_page_links_to_upload_only_with_writes(
    web: FlaskClient, writer: FlaskClient
) -> None:
    assert "Store a bundle" not in web.get("/certificates").get_data(as_text=True)
    assert "Store a bundle" in writer.get("/certificates").get_data(as_text=True)


def test_an_oversized_upload_is_refused_before_it_is_read(
    writer: FlaskClient, recorder: Recorder
) -> None:
    # The body is read into memory in full before it can be inspected, so the
    # limit has to be enforced by the server rather than by this code.
    import io as _io

    token = token_from(writer, "/certificates/upload")
    huge = b"-----BEGIN CERTIFICATE-----\n" + b"A" * 2_000_000
    response = writer.post(
        "/certificates/upload",
        data={
            "csrf_token": token,
            "name": "huge",
            "bundle": (_io.BytesIO(huge), "huge.pem"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 413
    assert recorder.writes == []
