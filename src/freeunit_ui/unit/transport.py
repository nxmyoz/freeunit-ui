"""Construction of HTTP clients for the FreeUnit control socket.

The control API is reachable either over a UNIX domain socket (the default and
the only one with peer-credential checking) or over TCP. Both are plain HTTP
from the client's point of view, so the only thing that varies is the transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from collections.abc import Iterator

# Hostname used for UNIX socket requests. It never leaves the process: httpx
# needs a syntactically valid URL, but the transport ignores the authority.
_UDS_HOST = "http://localhost"


def build_client(control: str, *, timeout: float = 10.0) -> httpx.Client:
    """Return an HTTP client bound to a control API endpoint.

    Args:
        control: Either an absolute filesystem path to a UNIX socket, or an
            ``http://host:port`` URL for a TCP control socket.
        timeout: Per-request timeout in seconds.

    Returns:
        A client whose base URL is set so callers use API paths like
        ``/config`` directly.

    Raises:
        ValueError: If ``control`` is neither an absolute path nor an http URL.
    """
    if control.startswith("/"):
        transport = httpx.HTTPTransport(uds=control)
        return httpx.Client(transport=transport, base_url=_UDS_HOST, timeout=timeout)

    if control.startswith(("http://", "https://")):
        return httpx.Client(base_url=control.rstrip("/"), timeout=timeout)

    msg = f"Control endpoint must be an absolute socket path or an http(s) URL, got {control!r}"
    raise ValueError(msg)


def iter_socket_candidates() -> Iterator[str]:
    """Yield the control socket paths distributions commonly use, best first."""
    yield "/run/freeunit.sock"
    yield "/var/run/freeunit.sock"
    yield "/run/unit.sock"
    yield "/var/run/unit.sock"
    yield "/var/run/control.unit.sock"
