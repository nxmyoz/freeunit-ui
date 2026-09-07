"""Clients for the FreeUnit control API.

``UnitClient`` can only read: it has no method that issues anything but a GET.
Writing is a separate subclass, so the read path cannot be tricked into writing
even when the application is configured to allow changes. Only the write views
ever construct a ``UnitWriteClient``, and those views are not registered at all
unless writes are enabled.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from .errors import UnitAPIError, UnitConnectionError, UnitError
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


def _segment(name: str) -> str:
    """Percent-encode ``name`` as a single, inescapable path segment.

    ``quote`` leaves dots alone, and a name of ".." would then be collapsed by
    URL normalisation before the request is sent: a certificate bundle called
    ".." becomes a PUT to the API root, carrying its private key. Relative
    segments are not addressable, so they are refused rather than encoded.
    """
    if name in {"", ".", ".."}:
        msg = f"{name!r} is not an addressable name"
        raise UnitError(msg)
    return quote(name, safe="")


class UnitWriteClient(UnitClient):
    """Read-write access to a FreeUnit control socket.

    Constructed only when ``enable_writes`` is set. Keeping these methods off
    ``UnitClient`` means a read view holding a client has no write method to
    call, by construction rather than by discipline.
    """

    def put_json(self, path: str, payload: Any) -> Any:
        """Replace the value at a control API path.

        Args:
            path: Absolute API path, such as ``/config/listeners``.
            payload: JSON-serialisable replacement value.

        Returns:
            The decoded success response from unitd.

        Raises:
            UnitConnectionError: The socket could not be reached.
            UnitAPIError: unitd rejected the document. For FreeUnit 1.36.1 and
                newer the error carries a JSON Pointer to the offending member.
        """
        return self._send("PUT", path, payload)

    def delete_path(self, path: str) -> Any:
        """Delete the value at a control API path.

        Args:
            path: Absolute API path to remove.

        Returns:
            The decoded success response from unitd.

        Raises:
            UnitConnectionError: The socket could not be reached.
            UnitAPIError: unitd refused the deletion.
        """
        return self._send("DELETE", path, None)

    def restart_application(self, name: str) -> Any:
        """Restart an application's processes.

        This is not a configuration change: nothing is stored, and the running
        configuration is untouched. Unit exposes it as a GET, which is why the
        interface wraps it in a form rather than linking to it.

        Raises:
            UnitError: The name is empty or a relative path segment.
            UnitConnectionError: The socket could not be reached.
            UnitAPIError: No such application, or unitd refused.
        """
        return self._send("GET", f"/control/applications/{_segment(name)}/restart", None)

    def put_certificate(self, name: str, bundle: bytes) -> Any:
        """Store a certificate bundle under ``name``.

        Args:
            name: Bundle name to create or replace. Must be addressable: an
                empty or relative name is refused.
            bundle: The PEM chain and its private key, sent as-is rather than
                as JSON, which is what the control API expects here.

        Raises:
            UnitError: The name is empty or a relative path segment.
            UnitConnectionError: The socket could not be reached.
            UnitAPIError: unitd rejected the bundle.
        """
        return self._send("PUT", f"/certificates/{_segment(name)}", None, content=bundle)

    def _send(self, method: str, path: str, payload: Any, *, content: bytes | None = None) -> Any:
        """Issue a mutating request and map failures onto the exception types."""
        try:
            if content is not None:
                response = self._http.request(method, path, content=content)
            elif payload is None:
                response = self._http.request(method, path)
            else:
                response = self._http.request(method, path, json=payload)
        except httpx.HTTPError as exc:
            msg = f"Cannot reach the FreeUnit control API: {exc}"
            raise UnitConnectionError(msg) from exc

        if response.is_success:
            return response.json()

        try:
            body = response.json()
        except ValueError:
            body = response.text
        raise UnitAPIError.from_payload(response.status_code, body)
