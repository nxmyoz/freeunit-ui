"""Tests for the command line entry point and the write-only accessors."""

from __future__ import annotations

from typing import Any

import pytest

from freeunit_ui import __main__ as entrypoint
from freeunit_ui.app import create_app
from freeunit_ui.extensions import get_snapshots, get_write_client
from freeunit_ui.settings import Settings


def test_main_serves_on_the_configured_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREEUNIT_UI_HOST", "127.0.0.1")
    monkeypatch.setenv("FREEUNIT_UI_PORT", "8123")
    seen: dict[str, Any] = {}

    def fake_run(self: Any, **kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr("flask.Flask.run", fake_run)
    entrypoint.main()
    assert seen == {"host": "127.0.0.1", "port": 8123}


def test_write_accessors_refuse_when_writes_are_disabled() -> None:
    # Reaching these without writes enabled would be a bug, not a misconfiguration,
    # so they raise rather than degrade.
    app = create_app(Settings())
    with app.test_request_context("/"):
        with pytest.raises(RuntimeError, match="Writes are disabled"):
            get_write_client()
        with pytest.raises(RuntimeError, match="Writes are disabled"):
            get_snapshots()
