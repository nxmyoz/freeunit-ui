"""Snapshots of the FreeUnit configuration.

The control API has no versioning and no undo. Anything that changes
configuration therefore records the previous document first, so a bad change can
be reversed without reconstructing it by hand.

Snapshots contain the complete configuration, including application paths and
which certificate bundles exist, so they are written 0600 in a directory created
0700.

The snapshot file holds nothing but the configuration document, so it stays
directly usable outside this interface:

    curl -X PUT --data-binary @20260906T101500123456Z.json \
        --unix-socket /run/freeunit.sock http://localhost/config

Who took it is kept in a small sibling ``.meta.json`` rather than wrapped around
the document, which also means listing snapshots does not read every one of them
in full.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Filename pattern: sortable, unambiguous, and safe on any filesystem.
_STAMP = "%Y%m%dT%H%M%S%fZ"
_SUFFIX = ".json"
_META_SUFFIX = ".meta.json"


class SnapshotError(RuntimeError):
    """A snapshot could not be written or read."""


class SnapshotNotFoundError(SnapshotError):
    """No snapshot exists under the requested name.

    Kept distinct from the base class so the web layer can tell "that name
    does not exist" (404) apart from "the store could not be read or
    written to" (a real failure, not a 404) - a disk-full or permission
    error must not be reported as if the snapshot simply never existed.
    """


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A stored configuration document."""

    name: str
    path: Path
    taken_at: datetime
    author: str | None = None
    reason: str | None = None

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

    def save(
        self,
        document: Any,
        *,
        author: str | None = None,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> Snapshot:
        """Write ``document`` as a new snapshot and prune old ones.

        Args:
            document: The configuration to store.
            author: Identity the proxy asserted for whoever caused this snapshot,
                when the interface is configured to read one.
            reason: What the operator said they were doing. Snapshots record
                what changed and who changed it; without this they cannot say
                why, which is the part that matters months later.
            now: Timestamp to use, for deterministic tests.

        Raises:
            SnapshotError: The directory or file could not be written.
        """
        taken_at = now or datetime.now(tz=UTC)
        name = taken_at.strftime(_STAMP)
        target = self._dir / f"{name}{_SUFFIX}"
        try:
            self._ensure_private_dir()
            # Write then chmod-by-open: never let the file exist world readable.
            self._write_private(target, json.dumps(document, indent=2, ensure_ascii=False))
            self._write_private(
                self._dir / f"{name}{_META_SUFFIX}",
                json.dumps({"taken_at": taken_at.isoformat(), "author": author, "reason": reason}),
            )
        except OSError as exc:
            msg = f"Cannot write a snapshot to {self._dir}: {exc}"
            raise SnapshotError(msg) from exc

        self._prune()
        return Snapshot(name=name, path=target, taken_at=taken_at, author=author, reason=reason)

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Hold an exclusive, process-wide lock across a read-check-write sequence.

        The control API has no compare-and-swap, so without this, two workers
        can both read the same current state, both pass a conflict check
        against it, and both write - the second silently clobbering the
        first's change, snapshot included. Every worker already shares this
        directory, so an flock on a file within it serializes the whole
        sequence across all of them without needing a separate lock service.

        Raises:
            SnapshotError: The lock file's directory could not be created.
        """
        try:
            self._ensure_private_dir()
        except OSError as exc:
            msg = f"Cannot create {self._dir} for the snapshot lock: {exc}"
            raise SnapshotError(msg) from exc

        fd = os.open(self._dir / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _ensure_private_dir(self) -> None:
        """Create the snapshot directory 0700, or tighten it if it already existed.

        ``mkdir``'s ``mode`` only applies to a directory it actually creates:
        a directory left behind by an older version of this code, or created
        by something else entirely, keeps whatever permissions it already
        had. Snapshots contain the complete configuration, so a mode not
        actually enforced here is a confidentiality gap, not a formality.
        """
        self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self._dir, 0o700)

    @staticmethod
    def _write_private(target: Path, text: str) -> None:
        """Create a file that is never momentarily readable by anyone else."""
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)

    def list(self) -> list[Snapshot]:
        """Return every stored snapshot, newest first."""
        if not self._dir.is_dir():
            return []
        found: list[Snapshot] = []
        for entry in self._dir.glob(f"*{_SUFFIX}"):
            if entry.name.endswith(_META_SUFFIX):
                continue
            name = entry.stem
            try:
                taken_at = datetime.strptime(name, _STAMP).replace(tzinfo=UTC)
            except ValueError:
                continue  # not one of ours
            author, reason = self._metadata(name)
            found.append(
                Snapshot(name=name, path=entry, taken_at=taken_at, author=author, reason=reason)
            )
        return sorted(found, key=lambda snap: snap.taken_at, reverse=True)

    def _metadata(self, name: str) -> tuple[str | None, str | None]:
        """Read the recorded author and reason, tolerating a missing or damaged sidecar."""
        try:
            meta = json.loads((self._dir / f"{name}{_META_SUFFIX}").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, None
        if not isinstance(meta, dict):
            return None, None
        author = meta.get("author")
        reason = meta.get("reason")
        return (
            author if isinstance(author, str) else None,
            reason if isinstance(reason, str) else None,
        )

    def get(self, name: str) -> Snapshot:
        """Return one snapshot by name.

        Raises:
            SnapshotNotFoundError: No snapshot of that name exists. The name is
                matched against the listing rather than used to build a path,
                so it cannot escape the snapshot directory.
        """
        for snapshot in self.list():
            if snapshot.name == name:
                return snapshot
        msg = f"No snapshot named {name!r}"
        raise SnapshotNotFoundError(msg)

    def _prune(self) -> None:
        """Delete the oldest snapshots beyond the retention limit."""
        for stale in self.list()[self._keep :]:
            stale.path.unlink(missing_ok=True)
            (self._dir / f"{stale.name}{_META_SUFFIX}").unlink(missing_ok=True)
