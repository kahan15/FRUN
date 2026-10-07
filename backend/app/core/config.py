from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = Field(
        default="postgresql+psycopg://territory:territory@localhost:5432/territory", repr=False
    )
    jwt_secret: str = Field(min_length=32, repr=False)
    access_minutes: int = Field(default=15, gt=0)
    refresh_days: int = Field(default=30, gt=0)
    environment: Literal["local", "test", "production"] = "local"
    allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])
    registration_enabled: bool = True
    recovery_delivery: Literal["disabled", "local_fake"] = "disabled"
    recovery_base_url: str = "http://127.0.0.1:8000"
    recovery_encryption_key: str = Field(default="", repr=False)
    recovery_minutes: int = Field(default=30, ge=5, le=60)
    simplify_m: float = Field(default=4, ge=0)
    close_gap_m: float = Field(default=30, ge=0)
    min_fragment_m2: float = Field(default=200, ge=0)
    accuracy_m: float = Field(default=30, gt=0)
    max_fix_gap_seconds: float = Field(default=30, gt=0)
    burst_ms: float = Field(default=12.5, gt=0)
    teleport_m: float = Field(default=250, gt=0)
    teleport_seconds: float = Field(default=120, gt=0)
    pace_margin: float = Field(default=0.05, ge=0, le=0.25)
    pace_records_men: list[tuple[float, float]] | None = None
    pace_records_women: list[tuple[float, float]] | None = None
    min_stride_m: float = Field(default=0.4, gt=0)
    max_stride_m: float = Field(default=2.6, gt=0)
    max_extent_m: float = Field(default=100000, gt=0)
    max_loop_vertices: int = Field(default=10000, gt=0, le=20000)
    max_loop_intersections: int = Field(default=20000, gt=0, le=50000)
    cooldown_hours: float = Field(default=6, ge=0)
    territory_days: int = Field(default=30, gt=0)
    monthly_reset: bool = False
    uploads_per_hour: int = Field(default=20, gt=0)
    max_body_bytes: int = Field(default=12_000_000, gt=0)
    body_timeout_seconds: float = Field(default=60, gt=0, le=300)
    db_connect_timeout_seconds: int = Field(default=5, gt=0, le=60)
    db_pool_timeout_seconds: int = Field(default=5, gt=0, le=60)
    db_statement_timeout_ms: int = Field(default=15000, gt=0, le=300000)
    db_lock_timeout_ms: int = Field(default=5000, gt=0, le=60000)
    db_idle_transaction_timeout_ms: int = Field(default=30000, gt=0, le=300000)
    login_ip_attempts_per_window: int = Field(default=60, gt=0)
    worker_interval_seconds: int = Field(default=60, gt=0)
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_topic: str = ""
    apns_key_path: str = ""
    apns_sandbox: bool = True

    @model_validator(mode="after")
    def production_safeguards(self):
        if self.recovery_delivery == "local_fake":
            if self.environment == "production":
                raise ValueError("Local fake email delivery cannot be enabled in production")
            from cryptography.fernet import Fernet

            try:
                Fernet(self.recovery_encryption_key.encode())
                url = urlsplit(self.recovery_base_url)
                if (
                    url.scheme != "http"
                    or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                    or url.username
                    or url.password
                    or url.query
                    or url.fragment
                    or url.path
                    or any(c.isspace() for c in self.recovery_base_url)
                ):
                    raise ValueError()
                _ = url.port
            except (ValueError, TypeError):
                raise ValueError(
                    "Local recovery requires a Fernet key and a loopback HTTP origin"
                ) from None
        if not self.allowed_hosts or any(
            not host or any(char in host for char in "/@ \t\r\n") for host in self.allowed_hosts
        ):
            raise ValueError("ALLOWED_HOSTS must contain hostnames, not URLs")
        if self.environment == "production":
            if any("*" in host for host in self.allowed_hosts):
                raise ValueError("Production requires explicit ALLOWED_HOSTS without wildcards")
            if (
                len(self.jwt_secret) < 48
                or len(set(self.jwt_secret)) < 12
                or self.jwt_secret.lower().startswith(("replace", "test", "change", "default"))
            ):
                raise ValueError("Production requires a freshly generated strong JWT_SECRET")
        return self

    @field_validator("pace_records_men", "pace_records_women")
    @classmethod
    def valid_curve(cls, value):
        if value is not None and (
            len(value) < 2
            or any(d <= 0 or t <= 0 for d, t in value)
            or any(b[0] <= a[0] or b[1] <= a[1] for a, b in zip(value, value[1:]))
        ):
            raise ValueError(
                "Pace anchors must have positive, strictly increasing distances and times"
            )
        return value


@lru_cache
def settings() -> Settings:
    return Settings()
