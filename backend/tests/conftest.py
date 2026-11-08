"""Shared fixtures."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture(autouse=True)
def _testclient_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Starlette's TestClient sends ``Host: testserver``; production only allows loopback."""
    monkeypatch.setenv("ALLOWED_HOSTS", "testserver")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at isolated temporary directories."""
    data = tmp_path / "data"
    inbox = tmp_path / "inbox"
    profiles = tmp_path / "profiles"
    for d in (data, inbox / "faturas", inbox / "extratos", profiles):
        d.mkdir(parents=True)
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text("{}\n")
    return Settings(
        data_dir=data,
        inbox_dir=inbox,
        profiles_dir=profiles,
        secrets_file=secrets,
        scan_interval_seconds=60,
        parse_timeout_seconds=10,
        backups_keep=5,
        enable_watcher=False,
    )


@pytest.fixture
def clock() -> FixedClock:
    """Clock fixed at 2026-10-12 10:00 America/Sao_Paulo."""
    return FixedClock(datetime(2026, 10, 12, 10, 0, tzinfo=TZ))
