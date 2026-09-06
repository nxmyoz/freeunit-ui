"""Structural comparison of two configuration documents.

Snapshots record what the configuration was, who changed it and why. Without a
diff they cannot answer the question that actually gets asked — what changed —
except by reading two documents side by side.

Differences are reported at RFC 6901 JSON Pointers, the same addressing unitd
uses for its own errors and this interface uses for advisory findings, so all
three read alike.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

Kind = Literal["added", "removed", "changed"]

#: Nesting beyond this is reported as a single change rather than descended
#: into. Configurations are shallow; a bound keeps a pathological document cheap.
_MAX_DEPTH = 12


@dataclass(frozen=True, slots=True)
class Change:
    """One difference between two documents."""

    pointer: str
    kind: Kind
    before: Any = None
    after: Any = None

    def rendered(self, value: Any) -> str:
        """Render one side compactly enough to read in a table."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @property
    def before_text(self) -> str:
        """The previous value, as displayed."""
        return self.rendered(self.before)

    @property
    def after_text(self) -> str:
        """The new value, as displayed."""
        return self.rendered(self.after)


def _walk(before: Any, after: Any, pointer: str, depth: int) -> list[Change]:
    """Compare two nodes, descending into objects while both sides are objects."""
    if before == after:
        return []

    if depth >= _MAX_DEPTH or not (isinstance(before, dict) and isinstance(after, dict)):
        return [Change(pointer=pointer or "/", kind="changed", before=before, after=after)]

    changes: list[Change] = []
    for key in sorted(set(before) | set(after)):
        here = f"{pointer}/{key}"
        if key not in after:
            changes.append(Change(pointer=here, kind="removed", before=before[key]))
        elif key not in before:
            changes.append(Change(pointer=here, kind="added", after=after[key]))
        else:
            changes += _walk(before[key], after[key], here, depth + 1)
    return changes


def compare(before: Any, after: Any) -> list[Change]:
    """Return every difference between two configuration documents.

    Args:
        before: The earlier document, typically a snapshot.
        after: The later document, typically the running configuration.

    Returns:
        Changes ordered by pointer. An empty list means the two are identical.
    """
    return _walk(before, after, "", 0)
