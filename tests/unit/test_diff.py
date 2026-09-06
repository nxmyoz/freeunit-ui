"""Tests for configuration comparison."""

from __future__ import annotations

from typing import Any

from freeunit_ui.diff import compare

BEFORE: dict[str, Any] = {
    "listeners": {"*:80": {"pass": "routes/main"}},
    "applications": {"blog": {"type": "python 3", "module": "m"}},
}


def test_identical_documents_have_no_changes() -> None:
    assert compare(BEFORE, BEFORE) == []


def test_added_member() -> None:
    after = {**BEFORE, "settings": {"http": {}}}
    changes = compare(BEFORE, after)
    assert [(c.kind, c.pointer) for c in changes] == [("added", "/settings")]


def test_removed_member() -> None:
    after = {"listeners": BEFORE["listeners"]}
    changes = compare(BEFORE, after)
    assert [(c.kind, c.pointer) for c in changes] == [("removed", "/applications")]


def test_changed_leaf_reports_both_sides() -> None:
    after = {**BEFORE, "listeners": {"*:80": {"pass": "routes/other"}}}
    change = compare(BEFORE, after)[0]
    assert change.kind == "changed"
    assert change.pointer == "/listeners/*:80/pass"
    assert change.before == "routes/main"
    assert change.after == "routes/other"


def test_changes_descend_into_nested_objects() -> None:
    after = {
        "listeners": BEFORE["listeners"],
        "applications": {"blog": {"type": "python 3", "module": "changed"}},
    }
    assert [c.pointer for c in compare(BEFORE, after)] == ["/applications/blog/module"]


def test_a_type_change_is_one_change_not_a_descent() -> None:
    changes = compare({"a": {"b": 1}}, {"a": "now a string"})
    assert [(c.kind, c.pointer) for c in changes] == [("changed", "/a")]


def test_lists_are_compared_whole() -> None:
    # Route arrays reorder meaningfully; a positional diff would mislead.
    changes = compare({"routes": [1, 2]}, {"routes": [1, 2, 3]})
    assert [(c.kind, c.pointer) for c in changes] == [("changed", "/routes")]


def test_changes_are_ordered_by_pointer() -> None:
    changes = compare({"b": 1, "a": 1}, {"b": 2, "a": 2})
    assert [c.pointer for c in changes] == ["/a", "/b"]


def test_root_replacement_is_reported_at_the_root() -> None:
    assert compare({"a": 1}, "not an object")[0].pointer == "/"


def test_rendering_keeps_strings_bare_and_serialises_the_rest() -> None:
    change = compare({"a": "one"}, {"a": {"two": 2}})[0]
    assert change.before_text == "one"
    assert change.after_text == '{"two": 2}'
    assert compare({"a": 1}, {"a": 1, "b": 2})[0].before_text == ""


def test_deep_nesting_is_bounded() -> None:
    def nest(depth: int, leaf: Any) -> Any:
        node = leaf
        for _ in range(depth):
            node = {"n": node}
        return node

    changes = compare(nest(30, 1), nest(30, 2))
    assert len(changes) == 1
    assert changes[0].pointer.count("/") <= 13
