"""Command line entry point.

This runs Flask's development server, which is single threaded and unhardened.
For anything beyond local use, serve the application through a real WSGI server
behind an authenticating reverse proxy; see docs/deployment.md.
"""

from __future__ import annotations

from .app import create_app
from .settings import Settings


def main() -> None:
    """Run the interface on the configured address."""
    settings = Settings()
    app = create_app(settings)
    app.run(host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
