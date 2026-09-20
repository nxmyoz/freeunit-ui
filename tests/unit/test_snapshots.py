"""Tests for the configuration snapshot store."""

from __future__ import annotations

import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from freeunit_ui.snapshots import SnapshotError, SnapshotNotFoundError, SnapshotStore

DOC = {"listeners": {"*:8080": {"pass": "applications/blog"}}}


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    snapshot = store.save(DOC)
    assert snapshot.load() == DOC


def test_snapshot_is_not_world_readable(tmp_path: Path) -> None:
    # Snapshots hold the entire configuration, including application paths.
    store = SnapshotStore(tmp_path / "snaps")
    snapshot = store.save(DOC)
    assert stat.S_IMODE(snapshot.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(snapshot.path.parent.stat().st_mode) == 0o700


def test_a_preexisting_loose_directory_is_tightened(tmp_path: Path) -> None:
    # mkdir's mode only applies to a directory it actually creates; a
    # directory left behind more loosely permissioned - by an older version
    # of this code, or by something else entirely - must still end up 0700
    # rather than keeping whatever it already had.
    directory = tmp_path / "snaps"
    directory.mkdir()
    directory.chmod(0o755)
    store = SnapshotStore(directory)
    store.save(DOC)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_listing_is_newest_first(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset in range(3):
        store.save({"n": offset}, now=base + timedelta(minutes=offset))
    listed = store.list()
    assert [snap.load()["n"] for snap in listed] == [2, 1, 0]


def test_listing_is_empty_before_the_directory_exists(tmp_path: Path) -> None:
    assert SnapshotStore(tmp_path / "absent").list() == []


def test_unrelated_files_are_ignored(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "notes.json").write_text("{}")
    assert SnapshotStore(tmp_path).list() == []


def test_pruning_keeps_the_newest(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path, keep=2)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset in range(5):
        store.save({"n": offset}, now=base + timedelta(minutes=offset))
    assert [snap.load()["n"] for snap in store.list()] == [4, 3]


def test_get_by_name(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    saved = store.save(DOC)
    assert store.get(saved.name).load() == DOC


def test_get_rejects_unknown_names(tmp_path: Path) -> None:
    # The name is matched against the listing, never used to build a path, so a
    # traversal attempt simply does not match anything.
    store = SnapshotStore(tmp_path)
    store.save(DOC)
    for name in ("nope", "../../etc/passwd", "/etc/passwd"):
        with pytest.raises(SnapshotNotFoundError):
            store.get(name)


def test_unwritable_directory_is_reported(tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("I am a file, not a directory")
    with pytest.raises(SnapshotError):
        SnapshotStore(blocker / "snaps").save(DOC)


def test_corrupt_snapshot_is_reported(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    snapshot = store.save(DOC)
    snapshot.path.write_text("{ not json")
    with pytest.raises(SnapshotError):
        snapshot.load()
