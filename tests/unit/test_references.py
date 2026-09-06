"""Tests for reference analysis."""

from __future__ import annotations

from typing import Any

from freeunit_ui.references import analyse

CONFIG: dict[str, Any] = {
    "listeners": {
        "*:443": {"pass": "routes/main", "tls": {"certificate": "example-org"}},
        "*:81": {"pass": "applications/gone"},
    },
    "routes": {
        "main": [
            {"action": {"pass": "applications/blog"}},
            {"action": {"share": "/srv", "fallback": {"pass": "applications/missing"}}},
        ]
    },
    "applications": {"blog": {}, "orphan": {}},
}


def test_resolved_references_are_found() -> None:
    report = analyse(CONFIG, {"example-org"})
    resolved = {r.target for r in report.references if r.resolved is True}
    assert resolved == {"routes/main", "example-org", "applications/blog"}


def test_broken_references_are_identified() -> None:
    report = analyse(CONFIG, {"example-org"})
    assert {r.target for r in report.broken} == {"applications/gone", "applications/missing"}


def test_fallbacks_are_followed() -> None:
    report = analyse(CONFIG, set())
    assert any(r.source.endswith("/fallback/pass") for r in report.references)


def test_destinations_built_from_variables_are_not_judged() -> None:
    # Unit expands these per request, so calling them broken would be wrong.
    report = analyse({"listeners": {"*:80": {"pass": "applications/$host"}}}, set())
    assert report.references[0].resolved is None
    assert report.broken == ()


def test_a_missing_certificate_bundle_is_broken() -> None:
    report = analyse(CONFIG, set())
    assert any(r.kind == "certificate" and r.is_broken for r in report.references)


def test_multiple_certificates_on_one_listener() -> None:
    config = {"listeners": {"*:443": {"tls": {"certificate": ["a", "b"]}}}}
    report = analyse(config, {"a"})
    assert [(r.target, r.resolved) for r in report.references] == [("a", True), ("b", False)]


def test_unnamed_route_array_resolves() -> None:
    config = {"listeners": {"*:80": {"pass": "routes"}}, "routes": [{"action": {}}]}
    assert analyse(config, set()).references[0].resolved is True


def test_pass_to_routes_when_routes_is_an_object_does_not_resolve() -> None:
    config = {"listeners": {"*:80": {"pass": "routes"}}, "routes": {"main": []}}
    assert analyse(config, set()).references[0].resolved is False


def test_unused_applications_and_certificates_are_listed() -> None:
    report = analyse(CONFIG, {"example-org", "never-used"})
    assert report.unused_applications == ("orphan",)
    assert report.unused_certificates == ("never-used",)


def test_an_empty_configuration_yields_an_empty_report() -> None:
    report = analyse({}, set())
    assert report.references == ()
    assert report.unused_applications == ()


def test_a_non_object_configuration_is_tolerated() -> None:
    assert analyse("nonsense", set()).references == ()


def test_unrecognised_destination_kinds_are_not_judged() -> None:
    # Newer releases add destinations such as upstreams; calling them broken
    # because this code has not heard of them would be wrong.
    config = {"listeners": {"*:80": {"pass": "upstreams/pool"}}}
    assert analyse(config, set()).references[0].resolved is None
