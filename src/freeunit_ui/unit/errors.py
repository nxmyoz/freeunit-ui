"""Exceptions raised when talking to the FreeUnit control API."""

from __future__ import annotations

from typing import Any


class UnitError(Exception):
    """Base class for every failure originating from the control API."""


class UnitConnectionError(UnitError):
    """The control socket could not be reached.

    This is usually a wrong socket path, missing permissions on the socket, or
    unitd not running. Since 1.36.0 unitd also rejects peers on a UNIX socket
    whose effective UID is neither root nor the user unitd runs as, which
    surfaces here as a refused connection rather than an HTTP error.
    """


class UnitAPIError(UnitError):
    """The control API rejected a request.

    Attributes:
        status_code: HTTP status returned by unitd.
        detail: The human readable error message from the API.
        location: RFC 6901 JSON Pointer to the offending configuration member,
            available since FreeUnit 1.36.1. An empty string means the document
            root; ``None`` means the server did not report a location.
        suggestion: Intended member name when the API recognises a close typo,
            available since FreeUnit 1.36.1.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        location: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Initialise the error from a decoded API error response."""
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.location = location
        self.suggestion = suggestion

    @classmethod
    def from_payload(cls, status_code: int, payload: Any) -> UnitAPIError:
        """Build an error from a decoded JSON error body.

        Unit reports failures as ``{"error": "...", "detail": "..."}`` and, since
        1.36.1, may add ``{"location": {"path": "/a/b"}, "suggestion": "..."}``.
        Anything unrecognised degrades to a generic message rather than raising.
        """
        if not isinstance(payload, dict):
            return cls(status_code, f"Unexpected error response: {payload!r}")

        detail = payload.get("detail") or payload.get("error") or "Unknown error"
        location = payload.get("location")
        path = location.get("path") if isinstance(location, dict) else None
        suggestion = payload.get("suggestion")
        return cls(
            status_code,
            str(detail),
            location=path if isinstance(path, str) else None,
            suggestion=suggestion if isinstance(suggestion, str) else None,
        )

    def __str__(self) -> str:
        """Render the error with its location and suggestion when present."""
        parts = [self.detail]
        if self.location is not None:
            parts.append(f"at {self.location or '/'}")
        if self.suggestion:
            parts.append(f"(did you mean {self.suggestion!r}?)")
        return " ".join(parts)
