"""A read-only client for the FreeUnit control API.

Only GET requests are implemented. Configuration writes are a privileged,
destructive operation and are intentionally absent from this release rather
than merely hidden behind a flag: an interface that cannot write cannot be
tricked into writing.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from .errors import UnitAPIError, UnitConnectionError
from .models import CertificateBundle, Status
from .transport import build_client


class UnitClient:
    """Read-only access to a FreeUnit control socket."""

    def __init__(self, http: httpx.Client) -> None:
        """Wrap an already configured HTTP client.

        Injecting the client keeps the class transport agnostic and lets tests
        supply ``httpx.MockTransport`` instead of a real socket.
        """
        self._http = http

    @classmethod
    def connect(cls, control: str, *, timeout: float = 10.0) -> Self:
        """Build a client for a socket path or ``http://`` control endpoint."""
        return cls(build_client(control, timeout=timeout))

    def __enter__(self) -> Self:
        """Enter a context manager that closes the underlying connection."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying HTTP client on exit."""
        self.close()

    def close(self) -> None:
        """Release the underlying connection pool."""
        self._http.close()

    def get_json(self, path: str) -> Any:
        """GET an arbitrary control API path and return the decoded JSON.

        Args:
            path: An absolute API path such as ``/config/listeners``.

        Returns:
            The decoded JSON body, which for the configuration tree may be any
            JSON type, not necessarily an object.

        Raises:
            UnitConnectionError: The socket could not be reached.
            UnitAPIError: unitd returned a non-success status.
        """
        try:
            response = self._http.get(path)
        except httpx.HTTPError as exc:
            msg = f"Cannot reach the FreeUnit control API: {exc}"
            raise UnitConnectionError(msg) from exc

        if response.is_success:
            return response.json()

        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        raise UnitAPIError.from_payload(response.status_code, payload)

    def get_config(self) -> Any:
        """Return the whole configuration document as opaque JSON."""
        return self.get_json("/config")

    def get_status(self) -> Status:
        """Return decoded runtime status."""
        return Status.model_validate(self.get_json("/status"))

    def get_certificates(self) -> dict[str, CertificateBundle]:
        """Return every stored certificate bundle, keyed by bundle name."""
        payload = self.get_json("/certificates")
        if not isinstance(payload, dict):
            return {}
        return {
            name: CertificateBundle.model_validate(bundle)
            for name, bundle in payload.items()
            if isinstance(bundle, dict)
        }
