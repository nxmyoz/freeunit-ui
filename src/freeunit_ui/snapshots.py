"""Snapshots of the FreeUnit configuration.

The control API has no versioning and no undo. Anything that changes
configuration therefore records the previous document first, so a bad change can
be reversed without reconstructing it by hand.

Snapshots contain the complete configuration, including application paths and
which certificate bundles exist, so they are written 0600 in a directory created
0700.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Filename pattern: sortable, unambiguous, and safe on any filesystem.
_STAMP = "%Y%m%dT%H%M%S%fZ"
_SUFFIX = ".json"


class SnapshotError(RuntimeError):
    """A snapshot could not be written or read."""


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A stored configuration document."""

    name: str
    path: Path
    taken_at: datetime

    def load(self) -> Any:
        """Return the stored configuration document."""
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            msg = f"Cannot read snapshot {self.name}: {exc}"
            raise SnapshotError(msg) from exc


class SnapshotStore:
    """Directory of configuration snapshots, newest first."""

    def __init__(self, directory: Path, *, keep: int = 50) -> None:
        """Configure the store without touching the filesystem yet."""
        self._dir = directory
        self._keep = keep

    def save(self, document: Any, *, now: datetime | None = None) -> Snapshot:
        """Write ``document`` as a new snapshot and prune old ones.

        Raises:
            SnapshotError: The directory or file could not be written.
        """
        taken_at = now or datetime.now(tz=UTC)
        name = taken_at.strftime(_STAMP)
        target = self._dir / f"{name}{_SUFFIX}"
        try:
            self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Write then chmod-by-open: never let the file exist world readable.
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, ensure_ascii=False)
        except OSError as exc:
            msg = f"Cannot write a snapshot to {self._dir}: {exc}"
            raise SnapshotError(msg) from exc

        self._prune()
        return Snapshot(name=name, path=target, taken_at=taken_at)

    def list(self) -> list[Snapshot]:
        """Return every stored snapshot, newest first."""
        if not self._dir.is_dir():
            return []
        found: list[Snapshot] = []
        for entry in self._dir.glob(f"*{_SUFFIX}"):
            name = entry.stem
            try:
                taken_at = datetime.strptime(name, _STAMP).replace(tzinfo=UTC)
            except ValueError:
                continue  # not one of ours
            found.append(Snapshot(name=name, path=entry, taken_at=taken_at))
        return sorted(found, key=lambda snap: snap.taken_at, reverse=True)

    def get(self, name: str) -> Snapshot:
        """Return one snapshot by name.

        Raises:
            SnapshotError: No snapshot of that name exists. The name is matched
                against the listing rather than used to build a path, so it
                cannot escape the snapshot directory.
        """
        for snapshot in self.list():
            if snapshot.name == name:
                return snapshot
        msg = f"No snapshot named {name!r}"
        raise SnapshotError(msg)

    def _prune(self) -> None:
        """Delete the oldest snapshots beyond the retention limit."""
        for stale in self.list()[self._keep :]:
            stale.path.unlink(missing_ok=True)
