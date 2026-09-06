"""Tests for certificate validity parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from freeunit_ui.unit.models import CertificateBundle, CertificateValidity

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "raw",
    ["Mar 14 12:00:00 2026 GMT", "Mar  4 12:00:00 2026 GMT", "2026-03-14T12:00:00+00:00"],
)
def test_known_timestamp_formats_parse(raw: str) -> None:
    assert CertificateValidity(until=raw).not_after is not None


def test_unknown_format_degrades_to_none() -> None:
    validity = CertificateValidity(until="whenever")
    assert validity.not_after is None
    assert validity.days_remaining(now=NOW) is None


def test_missing_until_is_none() -> None:
    assert CertificateValidity().days_remaining(now=NOW) is None


def test_days_remaining_is_negative_once_expired() -> None:
    validity = CertificateValidity(until="Jan  1 00:00:00 2025 GMT")
    days = validity.days_remaining(now=NOW)
    assert days is not None
    assert days < 0


def test_days_remaining_counts_forward() -> None:
    validity = CertificateValidity(until="Jan 31 00:00:00 2026 GMT")
    assert validity.days_remaining(now=NOW) == 30


def test_leaf_is_first_chain_entry_or_none() -> None:
    assert CertificateBundle().leaf is None
    bundle = CertificateBundle.model_validate(
        {"chain": [{"subject": {"common_name": "first"}}, {"subject": {"common_name": "second"}}]}
    )
    assert bundle.leaf is not None
    assert bundle.leaf.subject.common_name == "first"
