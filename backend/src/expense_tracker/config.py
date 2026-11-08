"""Runtime configuration read from environment variables (see docs/14-operacao.md)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"environment variable {name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"environment variable {name} must be positive, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Application settings. Paths are absolute inside the container."""

    data_dir: Path
    inbox_dir: Path
    profiles_dir: Path
    secrets_file: Path
    scan_interval_seconds: int = 60
    parse_timeout_seconds: int = 10
    backups_keep: int = 20
    log_level: str = "INFO"
    timezone: str = "America/Sao_Paulo"
    enable_watcher: bool = True
    examples_dir: Path = Path("/app/profiles-examples")

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables with documented defaults."""
        return cls(
            data_dir=Path(os.environ.get("DATA_DIR", "/app/data")),
            inbox_dir=Path(os.environ.get("INBOX_DIR", "/app/inbox")),
            profiles_dir=Path(os.environ.get("PROFILES_DIR", "/app/profiles")),
            secrets_file=Path(os.environ.get("SECRETS_FILE", "/run/secrets/pdf-passwords.yaml")),
            scan_interval_seconds=_int_env("SCAN_INTERVAL_SECONDS", 60),
            parse_timeout_seconds=_int_env("PARSE_TIMEOUT_SECONDS", 10),
            backups_keep=_int_env("BACKUPS_KEEP", 20),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            timezone=os.environ.get("TZ", "America/Sao_Paulo"),
            enable_watcher=os.environ.get("ENABLE_WATCHER", "1") not in ("0", "false", "no"),
            examples_dir=Path(os.environ.get("PROFILES_EXAMPLES_DIR", "/app/profiles-examples")),
        )
