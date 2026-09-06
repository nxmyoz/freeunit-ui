"""Wiring shared between the application factory and the web layer.

Keeping the registry key and its accessor here rather than in ``app`` means the
web layer does not import the application factory, which would be a cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import current_app

if TYPE_CHECKING:
    from collections.abc import Callable

    from .settings import Settings
    from .snapshots import SnapshotStore
    from .unit import UnitClient, UnitWriteClient

#: Key under which the control API client factory is stored on ``app.extensions``.
CLIENT_FACTORY_KEY = "freeunit_ui.client_factory"

#: Key under which the write-capable client factory is stored, when writes are enabled.
WRITE_CLIENT_FACTORY_KEY = "freeunit_ui.write_client_factory"

#: Key under which the snapshot store is stored, when writes are enabled.
SNAPSHOT_STORE_KEY = "freeunit_ui.snapshots"

#: Key under which the resolved settings are stored in ``app.config``.
SETTINGS_KEY = "SETTINGS"


def get_client() -> UnitClient:
    """Build a control API client using the factory registered on the app."""
    factory: Callable[[], UnitClient] = current_app.extensions[CLIENT_FACTORY_KEY]
    return factory()


def get_settings() -> Settings:
    """Return the settings the current application was built with."""
    settings: Settings = current_app.config[SETTINGS_KEY]
    return settings


def get_write_client() -> UnitWriteClient:
    """Build a write-capable control API client.

    Raises:
        RuntimeError: Writes are disabled. Reaching this means a write view was
            registered without ``enable_writes``, which would be a bug rather
            than a configuration mistake.
    """
    factory: Callable[[], UnitWriteClient] | None = current_app.extensions.get(
        WRITE_CLIENT_FACTORY_KEY
    )
    if factory is None:
        msg = "Writes are disabled; no write client is configured."
        raise RuntimeError(msg)
    return factory()


def get_snapshots() -> SnapshotStore:
    """Return the snapshot store.

    Raises:
        RuntimeError: Writes are disabled, so no store was configured.
    """
    store: SnapshotStore | None = current_app.extensions.get(SNAPSHOT_STORE_KEY)
    if store is None:
        msg = "Writes are disabled; no snapshot store is configured."
        raise RuntimeError(msg)
    return store
