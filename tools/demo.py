#!/usr/bin/env python
"""Run the interface against a fake FreeUnit, for looking at it without one.

Serves canned but realistic control API responses over a temporary UNIX socket
and points the application at it. Nothing here is part of the installed package.

    python tools/demo.py                 # read-only
    python tools/demo.py --writes        # editing enabled, snapshots in a temp dir
    python tools/demo.py --user alice    # pretend a proxy authenticated someone
"""

from __future__ import annotations

import argparse
import json
import socketserver
import sys
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from freeunit_ui.app import create_app
from freeunit_ui.settings import Settings


def _in_days(days: int) -> str:
    """Render a certificate expiry the way unitd does."""
    return (datetime.now(tz=UTC) + timedelta(days=days)).strftime("%b %d %H:%M:%S %Y GMT")


CONFIG: dict[str, Any] = {
    "settings": {"http": {"header_read_timeout": 30, "body_read_timeout": 30}},
    "listeners": {
        "*:80": {"pass": "routes/redirect"},
        "*:443": {
            "pass": "routes/main",
            "tls": {"certificate": "example-org", "session": {"cache_size": 1024}},
        },
        "127.0.0.1:8081": {"pass": "applications/internal-api"},
    },
    "routes": {
        "redirect": [{"action": {"return": 301, "location": "https://example.org$uri"}}],
        "main": [
            {"match": {"uri": "/static/*"}, "action": {"share": "/srv/www$uri"}},
            {"match": {"host": "blog.example.org"}, "action": {"pass": "applications/blog"}},
            {"action": {"pass": "applications/shop"}},
        ],
    },
    "applications": {
        "blog": {
            "type": "python 3",
            "path": "/srv/blog",
            "module": "blog.wsgi",
            "processes": {"max": 8, "spare": 2},
            "user": "www",
        },
        "shop": {
            "type": "php",
            "root": "/srv/shop/public",
            "script": "index.php",
            "options": {"file": "/etc/php/php.ini"},
        },
        "internal-api": {
            "type": "ruby",
            "script": "/srv/api/config.ru",
            "working_directory": "/srv/api",
        },
    },
    "access_log": {"path": "/var/log/freeunit/access.log", "format": "$remote_addr - $method"},
}

STATUS: dict[str, Any] = {
    "connections": {"accepted": 184223, "active": 37, "idle": 12, "closed": 184174},
    "requests": {"total": 942117},
    "applications": {
        "blog": {"processes": {"running": 4, "starting": 0, "idle": 2}, "requests": {"active": 5}},
        "shop": {"processes": {"running": 6, "starting": 1, "idle": 0}, "requests": {"active": 23}},
        "internal-api": {
            "processes": {"running": 1, "starting": 0, "idle": 1},
            "requests": {"active": 0},
        },
    },
    "telemetry": {"spans": {"exported": 48211, "failed": 17}},
}

CERTIFICATES: dict[str, Any] = {
    "example-org": {
        "key": "ECDSA (256 bits)",
        "chain": [
            {
                "subject": {
                    "common_name": "example.org",
                    "organization": "Example",
                    "alt_names": ["example.org", "www.example.org"],
                },
                "issuer": {"common_name": "Let's Encrypt R3"},
                "validity": {"since": _in_days(-60), "until": _in_days(51)},
            }
        ],
    },
    "blog-example-org": {
        "key": "RSA (2048 bits)",
        "chain": [
            {
                "subject": {"common_name": "blog.example.org", "alt_names": ["blog.example.org"]},
                "issuer": {"common_name": "Let's Encrypt R3"},
                "validity": {"since": _in_days(-80), "until": _in_days(9)},
            }
        ],
    },
    "legacy-internal": {
        "key": "RSA (4096 bits)",
        "chain": [
            {
                "subject": {"common_name": "internal.example.org"},
                "issuer": {"common_name": "Example Internal CA"},
                "validity": {"since": _in_days(-400), "until": _in_days(-14)},
            }
        ],
    },
}


def _resolve(path: str) -> Any:
    """Walk the canned documents the way the control API addresses them."""
    if path == "/status":
        return STATUS
    if path == "/certificates":
        return CERTIFICATES
    if not path.startswith("/config"):
        return None
    node: Any = CONFIG
    for raw in path[len("/config") :].strip("/").split("/"):
        if not raw:
            continue
        from urllib.parse import unquote

        key = unquote(raw)
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


class Handler(BaseHTTPRequestHandler):
    """Minimal stand-in for unitd's control API."""

    protocol_version = "HTTP/1.1"

    def _respond(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """Serve a canned document."""
        found = _resolve(self.path)
        if found is None:
            self._respond(404, {"error": "Value doesn't exist."})
        else:
            self._respond(200, found)

    def do_PUT(self) -> None:
        """Store a change, so the demo behaves like a server that remembers.

        Discarding writes would make the features built on top of them - diff,
        undo, and the check that what was stored matches what was sent -
        impossible to see.
        """
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        if self.path.startswith("/certificates/"):
            from urllib.parse import unquote

            CERTIFICATES[unquote(self.path[len("/certificates/") :])] = {
                "key": "stored by the demo",
                "chain": [
                    {
                        "subject": {"common_name": "uploaded.example"},
                        "issuer": {"common_name": "demo"},
                        "validity": {"since": _in_days(0), "until": _in_days(90)},
                    }
                ],
            }
            self._respond(200, {"success": "Certificate chain uploaded."})
            return

        try:
            document = json.loads(body)
        except ValueError:
            self._respond(400, {"error": "Invalid JSON."})
            return

        segments = [s for s in self.path[len("/config") :].split("/") if s]
        if not segments:
            CONFIG.clear()
            CONFIG.update(document)
        else:
            from urllib.parse import unquote

            node: Any = CONFIG
            for key in [unquote(s) for s in segments[:-1]]:
                node = node.setdefault(key, {})
            node[unquote(segments[-1])] = document
        self._respond(200, {"success": "Reconfiguration done."})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Keep the console readable."""


class UnixServer(socketserver.ThreadingUnixStreamServer):
    """Threaded UNIX-socket server for the fake control API."""

    allow_reuse_address = True


def main() -> None:
    """Start the fake control API and serve the interface against it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--writes", action="store_true", help="enable configuration editing")
    parser.add_argument("--user", default="", help="identity a proxy would have asserted")
    args = parser.parse_args()

    if args.writes and args.host not in {"127.0.0.1", "::1", "localhost"}:
        # This runs a writable interface with a fixed, public secret key.
        print(
            f"Refusing to serve --writes on {args.host}: the demo uses a fixed "
            "secret key and no authentication. Use the default loopback address.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    workdir = Path(tempfile.mkdtemp(prefix="freeunit-ui-demo-"))
    sock = workdir / "control.sock"
    server = UnixServer(str(sock), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    app = create_app(
        Settings(
            control=str(sock),
            enable_writes=args.writes,
            secret_key="demo-only-not-a-real-secret-key-0123456789" if args.writes else "",
            snapshot_dir=workdir / "snapshots",
            session_cookie_secure=False,
            auth_header="X-Demo-User" if args.user else "",
        )
    )

    if args.user:
        # Stand in for the reverse proxy asserting an identity.
        @app.before_request
        def _pretend_proxy() -> None:
            from flask import request

            request.environ["HTTP_X_DEMO_USER"] = args.user

    print(f"fake control API : {sock}")
    print(f"snapshots        : {workdir / 'snapshots'}")
    print(f"writes           : {'enabled' if args.writes else 'disabled'}")
    print(f"identity         : {args.user or 'none'}")
    print(f"\n  http://{args.host}:{args.port}/\n")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
