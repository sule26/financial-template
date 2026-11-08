"""Injectable clock. Business code never calls ``datetime.now()`` directly."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    """Source of "now" for the application."""

    def now(self) -> datetime: ...

    def today(self) -> date: ...


class SystemClock:
    """Real clock in the configured timezone."""

    def __init__(self, timezone: str = "America/Sao_Paulo") -> None:
        self._tz = ZoneInfo(timezone)

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    """Deterministic clock for tests; can be moved forward."""

    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def today(self) -> date:
        return self._current.date()

    def set(self, current: datetime) -> None:
        self._current = current
