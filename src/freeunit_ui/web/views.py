"""HTTP endpoints."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, render_template

from freeunit_ui.extensions import get_client, get_settings
from freeunit_ui.unit.errors import UnitAPIError, UnitConnectionError, UnitError

from .paths import InvalidPathError, breadcrumbs, split_config_path, to_api_path

bp = Blueprint("web", __name__)


def _pretty(payload: Any, *, limit: int) -> tuple[str, bool]:
    """Render a JSON document for display, truncating an oversized one.

    A configuration can be arbitrarily large, and embedding megabytes of it in a
    page helps nobody. Returns the text and whether it was truncated.
    """
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if len(text) <= limit:
        return text, False
    return text[:limit], True


@bp.get("/")
def dashboard() -> str:
    """Show runtime status and certificates needing attention."""
    settings = get_settings()
    with get_client() as client:
        status = client.get_status()
        certificates = client.get_certificates()

    expiring = []
    for name, bundle in sorted(certificates.items()):
        leaf = bundle.leaf
        if leaf is None:
            continue
        days = leaf.validity.days_remaining()
        if days is not None and days <= settings.cert_expiry_warning_days:
            expiring.append((name, leaf, days))

    return render_template(
        "dashboard.html",
        status=status,
        certificate_count=len(certificates),
        expiring=expiring,
        warning_days=settings.cert_expiry_warning_days,
    )


@bp.get("/config")
@bp.get("/config/<path:subpath>")
def config(subpath: str = "") -> str:
    """Browse the configuration tree."""
    segments = split_config_path(subpath)
    with get_client() as client:
        payload = client.get_json(to_api_path(segments))

    children: list[str] = sorted(payload) if isinstance(payload, dict) else []
    document, truncated = _pretty(payload, limit=get_settings().max_render_chars)
    return render_template(
        "config.html",
        segments=segments,
        crumbs=breadcrumbs(segments),
        children=children,
        document=document,
        truncated=truncated,
    )


@bp.get("/healthz")
def healthz() -> tuple[str, int, dict[str, str]]:
    """Liveness probe for a reverse proxy.

    Deliberately does not touch the control socket: a unitd outage should be
    visible on the pages, not remove this interface from the proxy's pool.
    """
    return "ok\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@bp.get("/certificates")
def certificates() -> str:
    """List stored certificate bundles with their expiry."""
    settings = get_settings()
    with get_client() as client:
        bundles = client.get_certificates()

    rows = [
        (name, bundle, bundle.leaf.validity.days_remaining() if bundle.leaf else None)
        for name, bundle in sorted(bundles.items())
    ]
    return render_template(
        "certificates.html", rows=rows, warning_days=settings.cert_expiry_warning_days
    )


@bp.app_errorhandler(InvalidPathError)
def _invalid_path(error: InvalidPathError) -> tuple[str, int]:
    """Render a 400 for an unaddressable configuration path."""
    return render_template("error.html", title="Invalid path", detail=str(error)), 400


@bp.app_errorhandler(UnitConnectionError)
def _unreachable(error: UnitConnectionError) -> tuple[str, int]:
    """Render a 502 when the control socket cannot be reached."""
    settings = get_settings()
    return (
        render_template(
            "error.html",
            title="FreeUnit is unreachable",
            detail=str(error),
            hint=(
                f"Checked {settings.control}. Confirm unitd is running and that this "
                "process runs as root or as the user unitd runs as: since 1.36.0 the "
                "control socket rejects other peers."
            ),
        ),
        502,
    )


@bp.app_errorhandler(UnitAPIError)
def _api_error(error: UnitAPIError) -> tuple[str, int]:
    """Render an error page for a rejected control API request."""
    status = 404 if error.status_code == 404 else 502
    return (
        render_template(
            "error.html",
            title="The control API rejected the request",
            detail=error.detail,
            location=error.location,
            suggestion=error.suggestion,
        ),
        status,
    )


@bp.app_errorhandler(UnitError)
def _unit_error(error: UnitError) -> tuple[str, int]:
    """Render a generic control API failure."""
    return render_template("error.html", title="Control API error", detail=str(error)), 502
