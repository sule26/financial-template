"""R14.9: price history of subscriptions and recurring purchases; R14.10: reactivate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from expense_tracker.domain.models import Interval, PriceEntry, RecurringPurchase, Subscription
from expense_tracker.domain.recurrence import (
    end,
    occurrences,
    recurring_charges,
    resume,
    subscription_charges,
)

D = Decimal


def _sub(**kw: object) -> Subscription:
    base: dict[str, object] = {
        "id": "sub_s",
        "description": "STREAMING",
        "amount": D("39.90"),
        "start_month": "2026-01",
        "card_id": "card_x",
    }
    return Subscription(**{**base, **kw})  # type: ignore[arg-type]


def _rec(**kw: object) -> RecurringPurchase:
    base: dict[str, object] = {
        "id": "rec_r",
        "description": "RACAO",
        "estimated_amount": D("100.00"),
        "every": Interval(value=1, unit="months"),
        "last_date": date(2026, 1, 10),
        "card_id": "card_x",
    }
    return RecurringPurchase(**{**base, **kw})  # type: ignore[arg-type]


def test_r14_9_subscription_price_changes_only_from_its_month() -> None:
    sub = _sub(
        price_history=[
            PriceEntry(from_month="2026-06", amount=D("44.90")),
            PriceEntry(from_month="2026-03", amount=D("42.90")),  # any order
        ]
    )
    months = ["2026-02", "2026-03", "2026-05", "2026-06", "2026-09"]
    got = {c.month: c.amount for c in subscription_charges(sub, months)}
    assert got == {
        "2026-02": D("39.90"),
        "2026-03": D("42.90"),
        "2026-05": D("42.90"),
        "2026-06": D("44.90"),
        "2026-09": D("44.90"),
    }


def test_r14_9_recurring_price_follows_the_purchase_month() -> None:
    rec = _rec(price_history=[PriceEntry(from_month="2026-04", amount=D("120.00"))])
    charges = recurring_charges(rec, ["2026-03", "2026-04", "2026-05"], lambda d: d.isoformat()[:7])
    assert [(c.month, c.amount) for c in charges] == [
        ("2026-03", D("100.00")),
        ("2026-04", D("120.00")),
        ("2026-05", D("120.00")),
    ]


def test_r14_9_without_history_the_base_price_is_used() -> None:
    assert _sub().amount_in("2030-01") == D("39.90")
    assert _rec().amount_in("2030-01") == D("100.00")


def test_r14_9_price_history_validation() -> None:
    with pytest.raises(ValidationError):
        PriceEntry(from_month="2026-01", amount=D("0"))
    with pytest.raises(ValidationError, match="distinct"):
        _sub(
            price_history=[
                PriceEntry(from_month="2026-03", amount=D("1")),
                PriceEntry(from_month="2026-03", amount=D("2")),
            ]
        )
    with pytest.raises(ValidationError, match="distinct"):
        _rec(
            price_history=[
                PriceEntry(from_month="2026-03", amount=D("1")),
                PriceEntry(from_month="2026-03", amount=D("2")),
            ]
        )


def test_r14_10_deactivate_and_reactivate_a_recurring_purchase() -> None:
    rec = _rec()
    off = end(rec)
    assert off.active is False
    assert occurrences(off, date(2026, 6, 30)) == []
    on = resume(off)
    assert on.active is True
    assert occurrences(on, date(2026, 3, 31)) == [date(2026, 2, 10), date(2026, 3, 10)]
    # reactivating from a date: that date is the next purchase
    later = resume(off, date(2026, 5, 20))
    assert occurrences(later, date(2026, 6, 30)) == [date(2026, 5, 20), date(2026, 6, 20)]


# ---------------------------------------------------------------- R14.11 pauses (history)


def test_r14_11_subscription_charged_only_while_active() -> None:
    from expense_tracker.domain.models import Pause

    sub = _sub(
        pauses=[
            Pause(from_month="2026-03", until_month="2026-05"),  # off Mar–May, back in June
            Pause(from_month="2026-09"),  # off again from September, still off
        ]
    )
    months = [f"2026-{m:02d}" for m in range(1, 13)]
    assert [c.month for c in subscription_charges(sub, months)] == [
        "2026-01",
        "2026-02",
        "2026-06",
        "2026-07",
        "2026-08",
    ]


def test_r14_11_recurring_occurrences_skip_paused_months() -> None:
    from expense_tracker.domain.models import Pause

    rec = _rec(pauses=[Pause(from_month="2026-03", until_month="2026-04")])
    assert occurrences(rec, date(2026, 6, 30)) == [
        date(2026, 2, 10),
        date(2026, 5, 10),
        date(2026, 6, 10),
    ]


def test_r14_11_end_and_resume_keep_the_history() -> None:
    rec = _rec()  # monthly from 2026-01-10
    off = end(rec, today=date(2026, 3, 1))  # Feb purchase never came: pause from February
    assert [(p.from_month, p.until_month) for p in off.pauses] == [("2026-02", None)]
    assert end(off, today=date(2026, 4, 1)) == off  # already off
    on = resume(off, date(2026, 6, 15), today=date(2026, 6, 1))
    assert [(p.from_month, p.until_month) for p in on.pauses] == [("2026-02", "2026-05")]
    assert occurrences(on, date(2026, 7, 31)) == [date(2026, 6, 15), date(2026, 7, 15)]


def test_r14_11_pause_validation() -> None:
    from expense_tracker.domain.models import Pause

    with pytest.raises(ValidationError, match="before"):
        Pause(from_month="2026-05", until_month="2026-04")
