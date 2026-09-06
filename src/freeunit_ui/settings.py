"""Runtime configuration, read from the environment.

Every setting is prefixed ``FREEUNIT_UI_``. Defaults are deliberately the safe
ones: loopback only, and the socket path used by the Gentoo package.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
