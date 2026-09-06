"""Tests for configuration path validation."""

from __future__ import annotations

import pytest

from freeunit_ui.web.paths import InvalidPathError, breadcrumbs, split_config_path, to_api_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", []), ("/", []), ("listeners", ["listeners"]), ("a/b/c", ["a", "b", "c"])],
)
def test_split_accepts_addressable_paths(raw: str, expected: list[str]) -> None:
    assert split_config_path(raw) == expected


@pytest.mark.parametrize("raw", ["a//b", "../etc", "a/../b", "a/./b"])
def test_split_rejects_relative_or_empty_segments(raw: str) -> None:
    with pytest.raises(InvalidPathError):
        split_config_path(raw)


def test_api_path_percent_encodes_segments() -> None:
    # Listener names such as "*:8080" contain characters that must not be read
    # as path separators or query delimiters.
    assert to_api_path(["listeners", "*:8080"]) == "/config/listeners/%2A%3A8080"


def test_api_path_root() -> None:
    assert to_api_path([]) == "/config"


def test_breadcrumbs_accumulate() -> None:
    assert breadcrumbs(["a", "b"]) == [("a", "a"), ("b", "a/b")]
