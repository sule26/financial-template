"""R14.30: gastos recorrentes "todo dia X do mês" (``day_of_month``): every occurrence on day X
(last day in shorter months), and a real purchase on another day never moves it off day X."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from expense_tracker.domain.models import RecurringPurchase
from expense_tracker.domain.recurrence import occurrences, reanchor


def _rec(**over: object) -> RecurringPurchase:
    data: dict[str, object] = {
        "id": "rec_x",
        "description": "ACADEMIA",
        "estimated_amount": "100.00",
        "every": {"value": 1, "unit": "months"},
        "last_date": "2026-09-30",
        "card_id": "card_x",
        "day_of_month": 31,
        **over,
    }
    return RecurringPurchase.model_validate(data)


def test_r14_30_every_occurrence_on_day_x_clamped() -> None:
    got = occurrences(_rec(), date(2027, 3, 31))
    assert got[:6] == [
        date(2026, 10, 31),
        date(2026, 11, 30),
        date(2026, 12, 31),
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
    ]
    # the last purchase itself (30/09) is never expected again
    assert date(2026, 9, 30) not in got


def test_r14_30_a_purchase_on_another_day_keeps_day_x() -> None:
    rec = _rec(day_of_month=10, last_date="2026-09-10")
    late = reanchor(rec, date(2026, 10, 12))  # paid 2 days late
    assert late.last_date == date(2026, 10, 10)
    assert occurrences(late, date(2026, 12, 31)) == [date(2026, 11, 10), date(2026, 12, 10)]
    early = reanchor(rec, date(2026, 10, 3))
    assert early.last_date == date(2026, 10, 10)
    # near a month boundary it picks the nearest day X
    edge = reanchor(_rec(day_of_month=2, last_date="2026-09-02"), date(2026, 10, 30))
    assert edge.last_date == date(2026, 11, 2)


def test_r14_30_without_day_the_real_date_is_the_anchor() -> None:
    rec = _rec(day_of_month=None, every={"value": 30, "unit": "days"})
    assert reanchor(rec, date(2026, 10, 12)).last_date == date(2026, 10, 12)


def test_r14_30_day_needs_a_monthly_interval_and_a_valid_day() -> None:
    with pytest.raises(ValidationError, match="day_of_month needs an interval in months"):
        _rec(every={"value": 30, "unit": "days"})
    with pytest.raises(ValidationError):
        _rec(day_of_month=32)


def test_r14_30_postpone_keeps_the_informed_date_then_back_to_day_x() -> None:
    from expense_tracker.domain.recurrence import postpone, skip

    rec = postpone(_rec(day_of_month=10, last_date="2026-09-10"), date(2026, 10, 20))
    got = occurrences(rec, date(2026, 12, 31))
    assert got == [date(2026, 10, 20), date(2026, 11, 10), date(2026, 12, 10)]
    # "Pular" the postponed date skips it
    assert occurrences(skip(rec, date(2026, 10, 20)), date(2026, 11, 30)) == [date(2026, 11, 10)]
