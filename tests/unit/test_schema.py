"""Tests for the guidance derived from the bundled specification."""

from __future__ import annotations

import pytest

from freeunit_ui.schema import SPEC_VERSION, describe
from freeunit_ui.schema import scaffolds as catalogue


def test_spec_version_is_recorded() -> None:
    # Guidance is only meaningful if it says which release it came from.
    assert SPEC_VERSION[0].isdigit()


def test_root_lists_the_configuration_sections() -> None:
    info = describe([])
    assert info is not None
    assert {m.name for m in info.members} == {
        "access_log",
        "applications",
        "listeners",
        "routes",
        "settings",
    }


def test_listener_members_are_described() -> None:
    info = describe(["listeners", "*:443"], {"pass": "routes/main"})
    assert info is not None
    assert {m.name for m in info.members} == {"pass", "tls", "forwarded"}
    assert info.member("pass") is not None
    assert info.member("pass").description


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("python 3", "module"), ("php", "root"), ("ruby", "script")],
)
def test_application_branch_follows_the_type(kind: str, expected: str) -> None:
    # configApplication is an anyOf; the document's own type picks the branch.
    info = describe(["applications", "app"], {"type": kind})
    assert info is not None
    assert expected in {m.name for m in info.members}
    assert expected in {m.name for m in info.members if m.required}


def test_common_members_are_merged_in_from_all_of() -> None:
    info = describe(["applications", "app"], {"type": "python 3"})
    assert info is not None
    names = {m.name for m in info.members}
    assert {"user", "group", "environment", "processes"} <= names


def test_defaults_and_enums_are_reported() -> None:
    info = describe(["applications", "app"], {"type": "python 3"})
    assert info is not None
    assert info.member("callable").default == "application"
    assert "python" in info.member("type").enum


def test_unknown_members_are_flagged_not_removed() -> None:
    # A newer server may know members this copy does not, so they are reported
    # rather than treated as errors.
    info = describe(["applications", "app"], {"type": "python 3", "invented_later": 1})
    assert info is not None
    assert info.unknown_members == ("invented_later",)


def test_undescribed_paths_return_none() -> None:
    assert describe(["not_a_section"]) is None
    assert describe(["listeners", "*:443", "pass", "deeper"]) is None


def test_describe_without_a_document_still_works() -> None:
    info = describe(["listeners", "*:443"])
    assert info is not None
    assert info.members


# --- scaffolds ------------------------------------------------------------


@pytest.mark.parametrize("scaffold", catalogue.SCAFFOLDS, ids=lambda s: s.key)
def test_every_scaffold_satisfies_its_schemas_required_members(scaffold) -> None:
    """The guard that keeps hand-written scaffolds honest.

    If a FreeUnit release adds a required member, this fails rather than the
    scaffold quietly producing a document the server will reject.
    """
    info = describe([*scaffold.applies_to, "example"], scaffold.document)
    assert info is not None, f"{scaffold.key} points at an undescribed path"
    required = {m.name for m in info.members if m.required}
    missing = required - set(scaffold.document)
    assert not missing, f"{scaffold.key} is missing required members: {sorted(missing)}"


@pytest.mark.parametrize("scaffold", catalogue.SCAFFOLDS, ids=lambda s: s.key)
def test_no_scaffold_invents_members(scaffold) -> None:
    info = describe([*scaffold.applies_to, "example"], scaffold.document)
    assert info is not None
    assert not info.unknown_members, f"{scaffold.key} uses unknown members"


def test_scaffolds_are_offered_on_a_member_not_the_section() -> None:
    # A new object is created at /config/applications/<name>, not at the map.
    assert catalogue.for_path(["applications"]) == ()
    assert {s.key for s in catalogue.for_path(["applications", "blog"])} == {
        "python-application",
        "php-application",
        "ruby-application",
    }
    assert {s.key for s in catalogue.for_path(["listeners", "*:80"])} == {
        "listener",
        "listener-tls",
    }


def test_scaffold_lookup() -> None:
    assert catalogue.get("python-application") is not None
    assert catalogue.get("nonexistent") is None


def test_scaffold_renders_as_json() -> None:
    rendered = catalogue.get("listener-tls").as_json()
    assert rendered.startswith("{")
    assert "certificate" in rendered
