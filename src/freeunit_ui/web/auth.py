"""Identity taken from the authenticating reverse proxy.

This interface does not authenticate anyone. It sits behind a proxy that does,
and reads the identity that proxy asserts so it can be shown and recorded.

That makes the header a trusted input, which is only true when nothing but the
proxy can reach the application. If the listener is reachable directly, a client
can set the header itself and the identity is worthless — so the header is not
read at all unless it is explicitly configured, and enabling ``require_auth``
without naming a header is refused at startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request

from freeunit_ui.extensions import get_settings

if TYPE_CHECKING:
    from flask import Flask


class NotAuthenticatedError(Exception):
    """A request arrived without the identity the proxy was supposed to assert."""


def current_identity() -> str | None:
    """Return the operator's identity, or ``None`` when it is not configured or absent."""
    header = get_settings().auth_header
    if not header:
        return None
    value = request.headers.get(header, "").strip()
    return value or None


def register_auth(app: Flask) -> None:
    """Refuse unauthenticated requests when the gate is enabled."""
    settings = app.config["SETTINGS"]
    if not settings.require_auth:
        return

    @app.before_request
    def _require_identity() -> None:
        # The liveness probe must answer for the proxy itself, which cannot
        # authenticate to a gate that exists to protect configuration.
        if request.endpoint == "web.healthz":
            return
        if current_identity() is None:
            msg = (
                f"No identity in {settings.auth_header}. This interface expects the "
                "reverse proxy in front of it to authenticate the request and assert "
                "who made it."
            )
            raise NotAuthenticatedError(msg)
