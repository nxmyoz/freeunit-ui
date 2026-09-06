"""WSGI entry point.

FreeUnit's Python module imports this and calls ``application``. Settings come
from the environment, which under FreeUnit means the application's
``environment`` object.

    "module": "freeunit_ui.wsgi",
    "callable": "application"
"""

from __future__ import annotations

from .app import create_app

application = create_app()
