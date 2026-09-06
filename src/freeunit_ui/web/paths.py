"""Validation of user supplied control API paths.

Config subpaths arrive from the URL and are appended to the control API path, so
they are untrusted input. Segments are validated rather than escaped: unitd
addresses configuration members by name, and a name containing a slash or a
relative segment cannot be expressed unambiguously anyway.
"""

from __future__ import annotations

from urllib.parse import quote

#: Segments that would change which resource is addressed.
_REJECTED = frozenset({"", ".", ".."})


class InvalidPathError(ValueError):
    """A requested configuration path is not addressable."""


def split_config_path(subpath: str) -> list[str]:
    """Split a URL subpath into validated configuration segments.

    Args:
        subpath: The raw ``<path:subpath>`` captured from the URL.

    Returns:
        The individual segments, empty for the configuration root.

    Raises:
        InvalidPathError: If any segment is empty or relative.
    """
    trimmed = subpath.strip("/")
    if not trimmed:
        return []

    segments = trimmed.split("/")
    if any(segment in _REJECTED for segment in segments):
        msg = f"Path contains an empty or relative segment: {subpath!r}"
        raise InvalidPathError(msg)
    return segments


def to_api_path(segments: list[str]) -> str:
    """Build the control API path addressing ``segments`` under ``/config``."""
    if not segments:
        return "/config"
    encoded = "/".join(quote(segment, safe="") for segment in segments)
    return f"/config/{encoded}"


def breadcrumbs(segments: list[str]) -> list[tuple[str, str]]:
    """Return ``(label, url_subpath)`` pairs for navigating back up the tree."""
    trail: list[tuple[str, str]] = []
    for index, segment in enumerate(segments):
        trail.append((segment, "/".join(segments[: index + 1])))
    return trail
