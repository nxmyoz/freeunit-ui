"""Cross-site request forgery protection for the write forms.

The interface has no authentication of its own and sits behind a proxy that
does, which means a browser reaching it already carries whatever the proxy
accepts. Without a token, any page an operator visits could submit a
configuration change on their behalf.

The token lives in a signed session cookie and is echoed in a hidden form field;
a request is accepted only when the two match.
"""

from __future__ import annotations

import secrets
from hmac import compare_digest

from flask import session

#: Session key holding the per-session token.
_SESSION_KEY = "csrf_token"

#: Form field carrying the echoed token.
FIELD_NAME = "csrf_token"

_TOKEN_BYTES = 32


class CsrfError(Exception):
    """A form submission carried a missing or mismatched token."""


def issue_token() -> str:
    """Return this session's token, creating one on first use."""
    token = session.get(_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        session[_SESSION_KEY] = token
    return token


def validate(submitted: str | None) -> None:
    """Check a submitted token against the session.

    Raises:
        CsrfError: The token is absent, or does not match the session.
    """
    expected = session.get(_SESSION_KEY)
    if not isinstance(expected, str) or not expected:
        msg = "No CSRF token in session; reload the form and try again."
        raise CsrfError(msg)
    # compare_digest rejects non-ASCII str arguments outright, and a submitted
    # token is attacker-controlled input - comparing the utf-8 bytes instead
    # keeps a stray non-ASCII character a mismatch rather than a 500.
    if not submitted or not compare_digest(expected.encode(), submitted.encode()):
        msg = "CSRF token missing or invalid."
        raise CsrfError(msg)
