"""Starting points for configuration objects.

These are written by hand rather than generated: a document assembled purely
from the schema is syntactically valid and operationally useless, because the
interesting part is the conventional shape, not the type of each member.

They are, however, *checked* against the schema by the test suite — every
scaffold must carry every member its schema marks required. If a FreeUnit
release adds one, the tests fail rather than the scaffold quietly going stale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Scaffold:
    """A starting point for one kind of configuration object."""

    key: str
    label: str
    summary: str
    schema: str
    applies_to: tuple[str, ...]
    document: dict[str, Any]

    def as_json(self) -> str:
        """Render the scaffold the way it appears in the editor."""
        return json.dumps(self.document, indent=2, ensure_ascii=False)


SCAFFOLDS: tuple[Scaffold, ...] = (
    Scaffold(
        key="python-application",
        label="Python application",
        summary="WSGI or ASGI application run from a module.",
        schema="configApplicationPython",
        applies_to=("applications",),
        document={
            "type": "python 3",
            "path": "/srv/example",
            "module": "example.wsgi",
            "callable": "application",
            "home": "/srv/example/.venv",
            "processes": {"max": 8, "spare": 2},
            "user": "www",
            "group": "www",
        },
    ),
    Scaffold(
        key="php-application",
        label="PHP application",
        summary="PHP application served from a document root.",
        schema="configApplicationPHP",
        applies_to=("applications",),
        document={
            "type": "php",
            "root": "/srv/example/public",
            "script": "index.php",
            "user": "www",
            "group": "www",
        },
    ),
    Scaffold(
        key="ruby-application",
        label="Ruby application",
        summary="Rack application run from a config.ru.",
        schema="configApplicationRuby",
        applies_to=("applications",),
        document={
            "type": "ruby",
            "script": "/srv/example/config.ru",
            "working_directory": "/srv/example",
            "user": "www",
            "group": "www",
        },
    ),
    Scaffold(
        key="listener",
        label="Listener",
        summary="Plain HTTP listener passing to a route or application.",
        schema="configListener",
        applies_to=("listeners",),
        document={"pass": "routes/main"},
    ),
    Scaffold(
        key="listener-tls",
        label="Listener with TLS",
        summary="HTTPS listener using a stored certificate bundle.",
        schema="configListener",
        applies_to=("listeners",),
        document={
            "pass": "routes/main",
            "tls": {"certificate": "example-org", "session": {"cache_size": 1024, "timeout": 300}},
        },
    ),
)


def for_path(segments: list[str]) -> tuple[Scaffold, ...]:
    """Return the scaffolds that make sense at a configuration path.

    A scaffold applies to a *member of* the section it names, since that is
    where a new object is created: ``/config/applications/blog``, not
    ``/config/applications``.
    """
    if len(segments) != 2:
        return ()
    return tuple(s for s in SCAFFOLDS if s.applies_to == (segments[0],))


def get(key: str) -> Scaffold | None:
    """Return one scaffold by key."""
    return next((s for s in SCAFFOLDS if s.key == key), None)
