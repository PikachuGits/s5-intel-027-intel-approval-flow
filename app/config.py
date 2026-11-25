"""Environment-backed settings; no secrets are read from files in this repository."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_timezone: ZoneInfo
    link_recheck_timeout_seconds: float
    reminder_service_url: str | None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigError("DATABASE_URL is required (e.g. postgresql+psycopg://user@host/db)")

    tz_name = os.environ.get("APP_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"APP_TIMEZONE is not a valid IANA timezone: {tz_name!r}") from exc

    raw_timeout = os.environ.get("LINK_RECHECK_TIMEOUT_SECONDS", "5").strip() or "5"
    try:
        timeout = float(raw_timeout)
        if timeout <= 0:
            raise ValueError
    except ValueError as exc:
        raise ConfigError(
            f"LINK_RECHECK_TIMEOUT_SECONDS must be a positive number, got {raw_timeout!r}"
        ) from exc

    # Integration point: production reminder service base URL. The stub client
    # shipped with this work order does not perform any network call.
    reminder_url = os.environ.get("REMINDER_SERVICE_URL", "").strip() or None

    return Settings(
        database_url=database_url,
        app_timezone=tz,
        link_recheck_timeout_seconds=timeout,
        reminder_service_url=reminder_url,
    )