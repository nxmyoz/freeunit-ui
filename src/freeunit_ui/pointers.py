"""RFC 6901 JSON Pointer construction.

A configuration member name is chosen by whoever writes the configuration, not
by this interface, so it can itself contain ``/`` or ``~`` - the two characters
JSON Pointer gives special meaning. Building a pointer by plain string
concatenation lets such a name split the path or point somewhere else
entirely; escaping each segment is what keeps the two reports below actually
addressing what they claim to.
"""

from __future__ import annotations


def escape(token: str) -> str:
    """Escape one path segment for use in a JSON Pointer.

    ``~`` must be escaped first, otherwise the ``~1`` produced for a literal
    ``/`` would itself be re-escaped into ``~01``.
    """
    return token.replace("~", "~0").replace("/", "~1")
