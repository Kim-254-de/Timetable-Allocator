"""Settings, read once from the environment (and `.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://allocator:allocator@localhost:5432/allocator"

    # SMARTTT, the only system the Allocator talks to.
    smarttt_base_url: str = "http://localhost:8000"
    smarttt_api_key: str = ""
    smarttt_timeout_seconds: float = 15.0
    # Reads from SMARTTT (published sections, lecturers' weeks) are cached at
    # most this long. Every write re-reads before checking.
    smarttt_cache_seconds: int = Field(default=60, ge=0, le=60)

    # Sign-in sessions: an opaque random token in an httpOnly cookie, stored hashed.
    session_cookie_name: str = "ta_session"
    csrf_cookie_name: str = "XSRF-TOKEN"
    csrf_header_name: str = "X-XSRF-TOKEN"
    session_idle_minutes: int = 120
    session_absolute_hours: int = 12
    # How often a session's roles (COD, department staff, timetabling office)
    # are re-read from SMARTTT, so a removed COD loses access quickly.
    identity_refresh_seconds: int = 300
    cookie_secure: bool = True
    cookie_domain: str | None = None

    cors_origins: list[str] = Field(default_factory=list)

    # Sign-in attempts per identifier and per client address, per window.
    login_max_attempts: int = 10
    login_window_seconds: int = 900

    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _production_requirements(self) -> Settings:
        if self.environment == "production":
            missing = [name for name, value in (("SMARTTT_API_KEY", self.smarttt_api_key),) if not value]
            if missing:
                raise ValueError(f"Missing required settings in production: {', '.join(missing)}")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
