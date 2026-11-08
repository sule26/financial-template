"""Health endpoint, settings and clock."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from expense_tracker.api.app import create_app
from expense_tracker.clock import FixedClock, SystemClock
from expense_tracker.config import Settings


def test_health_returns_ok(settings: Settings) -> None:
    client = TestClient(create_app(settings=settings))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ["DATA_DIR", "SCAN_INTERVAL_SECONDS", "LOG_LEVEL", "ENABLE_WATCHER"]:
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()
    assert s.data_dir == Path("/app/data")
    assert s.scan_interval_seconds == 60
    assert s.log_level == "INFO"
    assert s.enable_watcher is True


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "/x")
    monkeypatch.setenv("SCAN_INTERVAL_SECONDS", "5")
    monkeypatch.setenv("ENABLE_WATCHER", "0")
    s = Settings.from_env()
    assert s.data_dir == Path("/x")
    assert s.scan_interval_seconds == 5
    assert s.enable_watcher is False


@pytest.mark.parametrize("value", ["abc", "0", "-1"])
def test_settings_rejects_invalid_int(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SCAN_INTERVAL_SECONDS", value)
    with pytest.raises(ValueError, match="SCAN_INTERVAL_SECONDS"):
        Settings.from_env()


def test_fixed_clock() -> None:
    c = FixedClock(datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo")))
    assert c.today().isoformat() == "2026-10-12"
    c.set(datetime(2026, 11, 1, tzinfo=ZoneInfo("America/Sao_Paulo")))
    assert c.now().month == 11


def test_system_clock_uses_timezone() -> None:
    c = SystemClock("America/Sao_Paulo")
    assert c.now().tzinfo is not None
    assert c.today() == c.now().date()


def test_spa_fallback_serves_index(tmp_path: Path, settings: Settings) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "a.js").write_text("console.log(1)")
    (static / "favicon.svg").write_text("<svg/>")
    client = TestClient(create_app(settings=settings, static_dir=static))
    assert client.get("/resumo").text == "<html>app</html>"
    assert client.get("/assets/a.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/../../etc/passwd").text == "<html>app</html>"
