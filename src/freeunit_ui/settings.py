"""Runtime configuration, read from the environment.

Every setting is prefixed ``FREEUNIT_UI_``. Defaults are deliberately the safe
ones: loopback only, writes disabled, and the socket path used by the Gentoo
package.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """The interface was asked to start in an unsafe or impossible configuration."""


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_prefix="FREEUNIT_UI_", frozen=True)

    control: str = Field(
        default="/run/freeunit.sock",
        description="Control socket path, or an http:// URL for a TCP control socket.",
    )
    host: str = Field(
        default="127.0.0.1",
        description=(
            "Address the development server binds to. Loopback by default: this "
            "interface has no authentication of its own and must not be exposed "
            "directly to a network."
        ),
    )
    port: int = Field(default=8099, ge=1, le=65535)
    timeout: float = Field(default=10.0, gt=0)
    cert_expiry_warning_days: int = Field(
        default=30,
        ge=0,
        description="Highlight certificates expiring within this many days.",
    )

    max_render_chars: int = Field(
        default=512_000,
        ge=1_000,
        description="Truncate a rendered configuration document beyond this many characters.",
    )

    auth_header: str = Field(
        default="",
        description=(
            "Request header carrying the identity of the authenticated operator, "
            "set by the reverse proxy, for example X-Forwarded-User. Only safe "
            "when nothing but the proxy can reach this application: a client that "
            "can connect directly could otherwise set the header itself."
        ),
    )
    require_auth: bool = Field(
        default=False,
        description=(
            "Refuse every request that arrives without an identity in auth_header. "
            "Defence in depth: the proxy is still what authenticates, but a "
            "misconfigured proxy then fails closed instead of open."
        ),
    )

    enable_writes: bool = Field(
        default=False,
        description=(
            "Allow changing the FreeUnit configuration. Off by default: writing "
            "configuration is equivalent to root, because a configuration document "
            "can define an application with an arbitrary executable and user. When "
            "off, no write endpoint is registered at all."
        ),
    )
    secret_key: str = Field(
        default="",
        description=(
            "Signing key for the session cookie that carries the CSRF token. "
            "Required when writes are enabled. Must be stable across workers and "
            "restarts, so it is never generated automatically."
        ),
    )
    snapshot_dir: Path = Field(
        default=Path("/var/lib/freeunit-ui/snapshots"),
        description=(
            "Where the configuration is saved before every change. Snapshots "
            "contain the complete configuration and are written with mode 0600."
        ),
    )
    session_cookie_secure: bool = Field(
        default=True,
        description=(
            "Mark the session cookie Secure. Correct behind a TLS-terminating "
            "proxy, which is the supported deployment; turn it off only to test "
            "writes over plain HTTP on loopback."
        ),
    )
    snapshot_keep: int = Field(
        default=50, ge=1, description="Number of snapshots to retain before pruning."
    )

    @model_validator(mode="after")
    def _require_auth_needs_a_header(self) -> Settings:
        """Refuse a gate that cannot be enforced."""
        if self.require_auth and not self.auth_header:
            msg = (
                "FREEUNIT_UI_REQUIRE_AUTH needs FREEUNIT_UI_AUTH_HEADER to name the "
                "header the proxy sets, for example X-Forwarded-User."
            )
            raise ConfigurationError(msg)
        return self

    @model_validator(mode="after")
    def _writes_require_a_secret(self) -> Settings:
        """Refuse to enable writes without a stable signing key.

        Generating one automatically would appear to work and then silently break
        CSRF protection across workers and restarts, which is worse than failing
        to start.
        """
        if self.enable_writes and len(self.secret_key) < 32:
            msg = (
                "FREEUNIT_UI_ENABLE_WRITES requires FREEUNIT_UI_SECRET_KEY to be set "
                "to at least 32 characters. Generate one with: "
                "python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
            raise ConfigurationError(msg)
        return self
