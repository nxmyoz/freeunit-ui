"""Tests for the guidance derived from the bundled specification."""

from __future__ import annotations

import pytest

from freeunit_ui.schema import SPEC_VERSION, describe, first_word, validation
from freeunit_ui.schema import scaffolds as catalogue
from freeunit_ui.schema.scaffolds import Scaffold


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
    member = info.member("pass")
    assert member is not None
    assert member.description


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
    callable_member = info.member("callable")
    type_member = info.member("type")
    assert callable_member is not None
    assert type_member is not None
    assert callable_member.default == "application"
    assert "python" in type_member.enum


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
def test_every_scaffold_satisfies_its_schemas_required_members(scaffold: Scaffold) -> None:
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
def test_no_scaffold_invents_members(scaffold: Scaffold) -> None:
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
    scaffold = catalogue.get("listener-tls")
    assert scaffold is not None
    rendered = scaffold.as_json()
    assert rendered.startswith("{")
    assert "certificate" in rendered


# --- advisory checks ------------------------------------------------------


def test_missing_required_member_is_reported() -> None:
    findings = validation.check(["applications", "x"], {"type": "python 3"})
    assert [f.kind for f in findings] == ["missing_required"]
    assert "module" in findings[0].message


def test_wrong_type_is_reported_with_a_pointer() -> None:
    findings = validation.check(["applications", "x"], {"type": "python 3", "module": 123})
    assert findings[0].kind == "wrong_type"
    assert findings[0].pointer == "/module"


def test_type_checks_reach_nested_objects() -> None:
    findings = validation.check(["listeners", "*:443"], {"pass": "r", "tls": {"certificate": 123}})
    assert [f.pointer for f in findings] == ["/tls/certificate"]


def test_value_outside_an_enum_is_reported() -> None:
    findings = validation.check(["applications", "x"], {"type": "cobol", "module": "m"})
    assert [f.kind for f in findings] == ["not_in_enum"]


@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_first_word_of_a_blank_string_does_not_raise(blank: str) -> None:
    # A bare text.split()[0] raises IndexError on a blank or whitespace-only
    # string, which a stored "type" can be if unitd ever accepted one - a
    # plain str.split() call is empty rather than [""] for these inputs.
    assert first_word(blank) == blank


def test_a_blank_type_does_not_crash_branch_selection() -> None:
    # Goes through _select_branch, which used to call .split()[0] directly.
    assert describe(["applications", "x"], {"type": " "}) is not None


def test_a_blank_type_does_not_crash_the_enum_check() -> None:
    # Goes through validation.check's kind_unknown generator, the other
    # unguarded .split()[0] call.
    findings = validation.check(["applications", "x"], {"type": " ", "module": "m"})
    assert [f.kind for f in findings] == ["not_in_enum"]


def test_unknown_member_names_are_escaped_per_rfc_6901() -> None:
    # A member name is whatever the operator who wrote the configuration
    # chose; a "/" or "~" in it must not be read back as a path separator.
    findings = validation.check(
        ["applications", "x"], {"type": "python 3", "module": "m", "a/b~c": 1}
    )
    assert [f.pointer for f in findings] == ["/a~1b~0c"]


def test_an_unrecognised_type_does_not_make_real_members_look_unknown() -> None:
    # The branch cannot be resolved, so only shared members are described.
    # Reporting 'module' as unknown would be a false positive.
    findings = validation.check(["applications", "x"], {"type": "cobol", "module": "m"})
    assert not [f for f in findings if f.kind == "unknown_member"]


def test_unknown_members_are_reported_but_marked_uncertain() -> None:
    findings = validation.check(
        ["applications", "x"], {"type": "python 3", "module": "m", "invented": 1}
    )
    assert [f.kind for f in findings] == ["unknown_member"]
    assert findings[0].is_certain is False


def test_likely_mistakes_sort_before_drift() -> None:
    findings = validation.check(["applications", "x"], {"type": "python 3", "invented": 1})
    assert [f.kind for f in findings] == ["missing_required", "unknown_member"]


def test_booleans_do_not_satisfy_integers() -> None:
    findings = validation.check(
        ["applications", "x"], {"type": "python 3", "module": "m", "threads": True}
    )
    assert [f.kind for f in findings] == ["wrong_type"]


@pytest.mark.parametrize(
    ("segments", "document"),
    [
        (["applications", "x"], {"type": "python 3", "module": "app.wsgi"}),
        (["applications", "x"], {"type": "php", "root": "/srv"}),
        (["listeners", "*:443"], {"pass": "routes/main", "tls": {"certificate": "c"}}),
        (["applications", "x"], {"type": "python 3", "module": "m", "processes": 4}),
    ],
)
def test_valid_documents_produce_no_findings(
    segments: list[str], document: dict[str, object]
) -> None:
    assert validation.check(segments, document) == []


def test_undescribed_paths_are_not_judged() -> None:
    # Silence is the only honest answer for something the specification does
    # not cover; it must not be reported as invalid.
    assert validation.check(["not_a_section"], {"anything": 1}) == []


@pytest.mark.parametrize("scaffold", catalogue.SCAFFOLDS, ids=lambda s: s.key)
def test_no_scaffold_produces_findings(scaffold: Scaffold) -> None:
    assert validation.check([*scaffold.applies_to, "example"], scaffold.document) == []
