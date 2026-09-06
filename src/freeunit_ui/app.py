"""Application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask

from .extensions import CLIENT_FACTORY_KEY, SETTINGS_KEY
from .security import register_security_headers
from .settings import Settings
from .unit import UnitClient
from .web import bp as web_bp

if TYPE_CHECKING:
    from collections.abc import Callable


def create_app(
    settings: Settings | None = None,
    client_factory: Callable[[], UnitClient] | None = None,
) -> Flask:
    """Build the Flask application.

    Args:
        settings: Configuration to use. Read from the environment when omitted.
        client_factory: Callable returning a control API client. Injected by
            tests; by default a new client is built per request from
            ``settings.control`` so a restarted unitd is picked up without
            restarting this interface.

    Returns:
        A configured Flask application.
    """
    resolved = settings or Settings()
    # Templates and static assets live with the web layer they belong to.
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config[SETTINGS_KEY] = resolved

    def default_factory() -> UnitClient:
        return UnitClient.connect(resolved.control, timeout=resolved.timeout)

    app.extensions[CLIENT_FACTORY_KEY] = client_factory or default_factory

    register_security_headers(app)
    app.register_blueprint(web_bp)
    return app
