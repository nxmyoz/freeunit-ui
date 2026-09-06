"""Application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask

from .extensions import (
    CLIENT_FACTORY_KEY,
    SETTINGS_KEY,
    SNAPSHOT_STORE_KEY,
    WRITE_CLIENT_FACTORY_KEY,
)
from .security import register_security_headers
from .settings import Settings
from .snapshots import SnapshotStore
from .unit import UnitClient, UnitWriteClient
from .web import bp as web_bp
from .web.auth import current_identity, register_auth
from .web.writes import bp as writes_bp

if TYPE_CHECKING:
    from collections.abc import Callable


def create_app(
    settings: Settings | None = None,
    client_factory: Callable[[], UnitClient] | None = None,
    write_client_factory: Callable[[], UnitWriteClient] | None = None,
) -> Flask:
    """Build the Flask application.

    Args:
        settings: Configuration to use. Read from the environment when omitted.
        client_factory: Callable returning a read-only control API client.
            Injected by tests; by default a new client is built per request from
            ``settings.control`` so a restarted unitd is picked up without
            restarting this interface.
        write_client_factory: Callable returning a write-capable client. Only
            consulted when ``settings.enable_writes`` is set. Separate from
            ``client_factory`` so that the read path cannot be handed a client
            that is able to write.

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

    @app.context_processor
    def _template_globals() -> dict[str, object]:
        """Expose write availability and the operator's identity to templates."""
        return {"writes_enabled": resolved.enable_writes, "identity": current_identity()}

    register_security_headers(app)
    register_auth(app)
    app.register_blueprint(web_bp)

    if resolved.enable_writes:
        _enable_writes(app, resolved, write_client_factory)

    return app


def _enable_writes(
    app: Flask,
    settings: Settings,
    write_client_factory: Callable[[], UnitWriteClient] | None,
) -> None:
    """Register everything the mutating endpoints need.

    Called only when writes are enabled, so that with the default configuration
    the write routes do not exist at all rather than existing and refusing.
    """
    # Settings already refuses to construct with writes on and no usable key.
    app.secret_key = settings.secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=settings.session_cookie_secure,
    )

    def default_write_factory() -> UnitWriteClient:
        return UnitWriteClient.connect(settings.control, timeout=settings.timeout)

    app.extensions[WRITE_CLIENT_FACTORY_KEY] = write_client_factory or default_write_factory
    app.extensions[SNAPSHOT_STORE_KEY] = SnapshotStore(
        settings.snapshot_dir, keep=settings.snapshot_keep
    )
    app.register_blueprint(writes_bp)
