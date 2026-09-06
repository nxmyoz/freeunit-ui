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
    from .unit import UnitClient

#: Key under which the control API client factory is stored on ``app.extensions``.
CLIENT_FACTORY_KEY = "freeunit_ui.client_factory"

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
