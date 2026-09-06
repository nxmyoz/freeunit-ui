"""Advisory checks against the bundled specification.

Nothing here can refuse a configuration. unitd is the only authority on what is
valid, and the bundled specification is pinned to one release while the server
is not, so a check that blocked would eventually block something correct.

These findings exist to catch a typo at the form instead of after the round
trip. They are reported the way unitd reports its own: with an RFC 6901 JSON
Pointer at the member concerned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from . import accepted_types, describe, raw_properties

#: How far to descend. Configurations nest, but not deeply, and a bound keeps a
#: hostile or generated document from costing anything noticeable.
_MAX_DEPTH = 6

Kind = Literal["missing_required", "unknown_member", "wrong_type", "not_in_enum"]


@dataclass(frozen=True, slots=True)
class Finding:
    """Something the specification suggests is wrong, at a JSON Pointer."""

    pointer: str
    kind: Kind
    message: str

    @property
    def is_certain(self) -> bool:
        """Whether this is likely a real mistake rather than specification drift.

        An unrecognised member is the one finding a newer server would disagree
        with, so it is presented differently.
        """
        return self.kind != "unknown_member"


def _check(segments: list[str], value: Any, pointer: str, depth: int) -> list[Finding]:
    """Check one node against the specification, then descend into its members."""
    info = describe(segments, value)
    if info is None or not isinstance(value, dict):
        return []

    props = raw_properties(segments, value)
    findings: list[Finding] = []

    for member in info.members:
        if member.required and member.name not in value:
            findings.append(
                Finding(
                    pointer=pointer or "/",
                    kind="missing_required",
                    message=f"{member.name!r} is required here.",
                )
            )

    # When the document's own type is not one the specification knows, the
    # branch could not be resolved and only the shared members are described.
    # Member names are then unjudgeable, so they are not reported.
    kind_unknown = any(
        member.enum
        and isinstance(value.get(member.name), str)
        and value[member.name].split()[0] not in member.enum
        for member in info.members
        if member.name == "type"
    )

    findings += (
        []
        if kind_unknown
        else [
            Finding(
                pointer=f"{pointer}/{name}",
                kind="unknown_member",
                message=(
                    f"{name!r} is not in the bundled specification. That may simply mean "
                    "your server is newer than it."
                ),
            )
            for name in info.unknown_members
        ]
    )

    for member in info.members:
        if member.name not in value:
            continue
        given = value[member.name]
        here = f"{pointer}/{member.name}"

        accepted = accepted_types(props.get(member.name))
        if accepted and not _matches(given, accepted):
            findings.append(
                Finding(
                    pointer=here,
                    kind="wrong_type",
                    message=(
                        f"expected {member.type_name or 'a different type'}, "
                        f"got {type(given).__name__}."
                    ),
                )
            )
            continue

        if member.enum and isinstance(given, str):
            # Application types carry a version, as in "python 3".
            head = given.split()[0] if given else given
            if head not in member.enum:
                findings.append(
                    Finding(
                        pointer=here,
                        kind="not_in_enum",
                        message=f"{given!r} is not one of: {', '.join(member.enum)}.",
                    )
                )

        if depth < _MAX_DEPTH and isinstance(given, dict):
            findings += _check([*segments, member.name], given, here, depth + 1)

    return findings


def check(segments: list[str], document: Any) -> list[Finding]:
    """Return everything the specification suggests is wrong with ``document``.

    Args:
        segments: Configuration path below ``/config`` the document belongs at.
        document: The document as submitted.

    Returns:
        Findings, likely mistakes before specification drift. An empty list
        means the bundled specification has no objection, which is not a
        promise that unitd will accept it.
    """
    findings = _check(segments, document, "", 0)
    findings.sort(key=lambda f: (not f.is_certain, f.pointer))
    return findings


def _matches(value: Any, accepted: tuple[type, ...]) -> bool:
    """Whether ``value`` is one of the accepted types, keeping bool out of int."""
    if isinstance(value, bool) and bool not in accepted:
        return False
    return isinstance(value, accepted)
