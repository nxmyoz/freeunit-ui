"""Typed views over the parts of the control API whose shape is stable.

Only ``/status`` and ``/certificates`` are modelled. ``/config`` deliberately is
not: its schema is large, evolves every release, and is fully user defined, so
it is carried as opaque JSON and rendered generically.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

# Formats unitd has used for certificate validity timestamps.
_VALIDITY_FORMATS = ("%b %d %H:%M:%S %Y %Z", "%b %e %H:%M:%S %Y %Z", "%Y-%m-%dT%H:%M:%S%z")


class _Model(BaseModel):
    """Base model that tolerates fields added by newer FreeUnit releases."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Connections(_Model):
    """Connection counters reported by ``/status/connections``."""

    accepted: int = 0
    active: int = 0
    idle: int = 0
    closed: int = 0


class Requests(_Model):
    """Request counters reported by ``/status/requests``."""

    total: int = 0


class AppProcesses(_Model):
    """Per-application process counters."""

    running: int = 0
    starting: int = 0
    idle: int = 0


class AppRequests(_Model):
    """Per-application request counters."""

    active: int = 0


class ApplicationStatus(_Model):
    """Runtime status of a single configured application."""

    processes: AppProcesses = Field(default_factory=AppProcesses)
    requests: AppRequests = Field(default_factory=AppRequests)


class TelemetrySpans(_Model):
    """OpenTelemetry span export counters, added in FreeUnit 1.36.1."""

    exported: int = 0
    failed: int = 0


class Telemetry(_Model):
    """Telemetry health.

    Absent entirely unless unitd was built with OpenTelemetry support, telemetry
    is configured, and the exporter was built successfully.
    """

    spans: TelemetrySpans = Field(default_factory=TelemetrySpans)


class Status(_Model):
    """Decoded ``/status`` document."""

    connections: Connections = Field(default_factory=Connections)
    requests: Requests = Field(default_factory=Requests)
    applications: dict[str, ApplicationStatus] = Field(default_factory=dict)
    telemetry: Telemetry | None = None


class CertificateSubject(_Model):
    """Subject or issuer distinguished name of a certificate."""

    common_name: str | None = None
    country: str | None = None
    state_or_province: str | None = None
    organization: str | None = None
    alt_names: list[str] = Field(default_factory=list)


class CertificateValidity(_Model):
    """Validity window of a certificate, as reported by unitd."""

    since: str | None = None
    until: str | None = None

    @staticmethod
    def _parse(value: str | None) -> datetime | None:
        """Parse a unitd timestamp, returning ``None`` if the format is unknown."""
        if not value:
            return None
        for fmt in _VALIDITY_FORMATS:
            try:
                parsed = datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return None

    @property
    def not_after(self) -> datetime | None:
        """Expiry as a datetime, or ``None`` when unitd used an unknown format."""
        return self._parse(self.until)

    def days_remaining(self, *, now: datetime | None = None) -> int | None:
        """Whole days until expiry, negative once expired, ``None`` if unparseable."""
        expiry = self.not_after
        if expiry is None:
            return None
        reference = now or datetime.now(tz=UTC)
        return (expiry - reference).days


class CertificateChainEntry(_Model):
    """One certificate within a stored bundle's chain."""

    subject: CertificateSubject = Field(default_factory=CertificateSubject)
    issuer: CertificateSubject = Field(default_factory=CertificateSubject)
    validity: CertificateValidity = Field(default_factory=CertificateValidity)


class CertificateBundle(_Model):
    """A certificate bundle stored under ``/certificates/{name}``."""

    key: str | None = None
    chain: list[CertificateChainEntry] = Field(default_factory=list)

    @property
    def leaf(self) -> CertificateChainEntry | None:
        """The end-entity certificate, which unitd stores first in the chain."""
        return self.chain[0] if self.chain else None
