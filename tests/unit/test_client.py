"""Tests for the control API client and its error mapping."""

from __future__ import annotations

import httpx
import pytest

from freeunit_ui.unit import UnitAPIError, UnitClient, UnitConnectionError, UnitWriteClient
from freeunit_ui.unit.transport import build_client, iter_socket_candidates
from tests.conftest import DEFAULT_ROUTES, make_client, make_handler


def test_get_status_decodes_counters() -> None:
    with make_client(make_handler(DEFAULT_ROUTES)) as client:
        status = client.get_status()
    assert status.connections.active == 2
    assert status.requests.total == 41
    assert status.applications["blog"].processes.running == 2


def test_status_telemetry_is_optional() -> None:
    routes = {"/status": {"connections": {"active": 1}}}
    with make_client(make_handler(routes)) as client:
        status = client.get_status()
    assert status.telemetry is None
    assert status.connections.active == 1


def test_unknown_fields_from_newer_releases_are_ignored() -> None:
    routes = {"/status": {"connections": {"active": 1, "invented_later": 5}}}
    with make_client(make_handler(routes)) as client:
        assert client.get_status().connections.active == 1


def test_get_certificates_skips_non_object_entries() -> None:
    routes = {"/certificates": {"good": {"chain": []}, "bogus": "not-an-object"}}
    with make_client(make_handler(routes)) as client:
        bundles = client.get_certificates()
    assert set(bundles) == {"good"}


def test_get_certificates_tolerates_non_object_document() -> None:
    with make_client(make_handler({"/certificates": []})) as client:
        assert client.get_certificates() == {}


def test_connection_failure_is_wrapped() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with make_client(explode) as client, pytest.raises(UnitConnectionError):
        client.get_status()


def test_api_error_carries_pointer_and_suggestion() -> None:
    body = {
        "error": "Invalid configuration.",
        "detail": "Unknown parameter.",
        "location": {"path": "/listeners/*:8080"},
        "suggestion": "pass",
    }
    with (
        make_client(make_handler(error_body=body, status_code=400)) as client,
        pytest.raises(UnitAPIError) as excinfo,
    ):
        client.get_config()

    error = excinfo.value
    assert error.status_code == 400
    assert error.location == "/listeners/*:8080"
    assert error.suggestion == "pass"
    assert "did you mean 'pass'" in str(error)


def test_api_error_without_optional_members() -> None:
    with (
        make_client(make_handler(error_body={"error": "Nope."}, status_code=404)) as client,
        pytest.raises(UnitAPIError) as excinfo,
    ):
        client.get_config()
    assert excinfo.value.location is None
    assert str(excinfo.value) == "Nope."


def test_api_error_from_non_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with make_client(handler) as client, pytest.raises(UnitAPIError) as excinfo:
        client.get_config()
    assert excinfo.value.status_code == 500


def test_api_error_from_unexpected_payload_shape() -> None:
    with (
        make_client(make_handler(error_body=["unexpected"], status_code=400)) as client,
        pytest.raises(UnitAPIError) as excinfo,
    ):
        client.get_config()
    assert "Unexpected error response" in excinfo.value.detail


def test_build_client_accepts_socket_path_and_url() -> None:
    with build_client("/run/freeunit.sock") as unix_client:
        assert unix_client.base_url.host == "localhost"
    with build_client("http://127.0.0.1:8080/") as tcp_client:
        assert tcp_client.base_url.port == 8080


def test_build_client_rejects_other_forms() -> None:
    with pytest.raises(ValueError, match="absolute socket path"):
        build_client("relative/path.sock")


def test_socket_candidates_are_absolute() -> None:
    candidates = list(iter_socket_candidates())
    assert candidates
    assert all(path.startswith("/") for path in candidates)


def test_connect_builds_a_working_client_object() -> None:
    client = UnitClient.connect("/definitely/missing.sock")
    try:
        with pytest.raises(UnitConnectionError):
            client.get_status()
    finally:
        client.close()


def test_write_client_puts_and_deletes() -> None:
    seen: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content))
        return httpx.Response(200, json={"success": "Reconfiguration done."})

    client = UnitWriteClient(
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://unit")
    )
    with client:
        client.put_json("/config/listeners", {"*:80": {}})
        client.delete_path("/config/listeners/*:80")

    assert seen[0][:2] == ("PUT", "/config/listeners")
    assert b'"*:80"' in seen[0][2]
    assert seen[1][:2] == ("DELETE", "/config/listeners/*:80")
    assert seen[1][2] == b""


def test_write_rejection_is_mapped_to_an_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Invalid.", "location": {"path": "/x"}})

    client = UnitWriteClient(
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://unit")
    )
    with client, pytest.raises(UnitAPIError) as excinfo:
        client.put_json("/config", {})
    assert excinfo.value.location == "/x"


def test_write_rejection_with_a_non_json_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = UnitWriteClient(
        httpx.Client(transport=httpx.MockTransport(handler), base_url="http://unit")
    )
    with client, pytest.raises(UnitAPIError) as excinfo:
        client.delete_path("/config/x")
    assert excinfo.value.status_code == 500


def test_write_connection_failure_is_wrapped() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = UnitWriteClient(
        httpx.Client(transport=httpx.MockTransport(explode), base_url="http://unit")
    )
    with client, pytest.raises(UnitConnectionError):
        client.put_json("/config", {})
