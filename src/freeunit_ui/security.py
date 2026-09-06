"""Response hardening applied to every rendered page.

The interface ships no JavaScript, which lets the policy forbid script entirely
rather than allow-listing it. Keep it that way: any inline handler added later
silently weakens this to nothing unless the policy is revisited.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask, Response

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'none'",
        "style-src 'self'",
        "img-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
    )
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store",
}


def register_security_headers(app: Flask) -> None:
    """Attach the hardening headers to every response of ``app``."""

    @app.after_request
    def _apply(response: Response) -> Response:
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
