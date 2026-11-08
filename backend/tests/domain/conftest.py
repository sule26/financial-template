"""Fixtures for domain tests; the builders themselves live in ``builders.py``."""

from __future__ import annotations

from datetime import date

import pytest
from builders import Builders

from expense_tracker.domain.ledger import projection_months


@pytest.fixture(scope="session")
def mk() -> type[Builders]:
    """Domain model builders (session-scoped so hypothesis tests can use them)."""
    return Builders


@pytest.fixture
def today() -> date:
    """Same day as the shared ``clock`` fixture (2026-10-12)."""
    return date(2026, 10, 12)


@pytest.fixture
def window(today: date) -> list[str]:
    """The 12-month projection window for ``today``."""
    return projection_months(today)
