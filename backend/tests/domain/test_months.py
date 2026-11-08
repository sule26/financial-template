"""Months, invoice month and H(card) (docs/07 "Mês de fatura", "Mês corrente de um cartão")."""

from __future__ import annotations

from datetime import date

import pytest

from expense_tracker.domain.models import BillingEntry
from expense_tracker.domain.months import (
    add_interval,
    add_months,
    billing_for,
    clamp_day,
    closing_after,
    current_invoice_month,
    due_date_for_closing,
    due_date_of_month,
    invoice_month,
    month_diff,
    month_of,
    month_range,
    parse_month,
)


def billing(*entries: tuple[str, int, int]) -> list[BillingEntry]:
    return [BillingEntry(from_month=m, closing_day=c, due_day=d) for m, c, d in entries]


CLOSE3_DUE10 = billing(("2020-01", 3, 10))
CLOSE25_DUE5 = billing(("2020-01", 25, 5))


# ---------------------------------------------------------------- month arithmetic


def test_month_of_and_parse_month() -> None:
    assert month_of(date(2026, 9, 2)) == "2026-09"
    assert parse_month("2027-12") == (2027, 12)


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "26-01", "2026/01", "2026-1"])
def test_parse_month_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_month(bad)


@pytest.mark.parametrize(
    ("month", "delta", "expected"),
    [("2026-12", 1, "2027-01"), ("2027-01", -1, "2026-12"), ("2026-08", 9, "2027-05"),
     ("2026-03", -15, "2024-12"), ("2026-03", 0, "2026-03")],
)  # fmt: skip
def test_add_months_wraps_years(month: str, delta: int, expected: str) -> None:
    assert add_months(month, delta) == expected


def test_month_diff_and_range() -> None:
    assert month_diff("2027-02", "2026-11") == 3
    assert month_diff("2026-11", "2027-02") == -3
    assert month_range("2026-11", 3) == ["2026-11", "2026-12", "2027-01"]
    assert month_range("2026-11", 0) == []


@pytest.mark.parametrize(
    ("y", "m", "d", "expected"),
    [(2026, 2, 31, date(2026, 2, 28)), (2028, 2, 31, date(2028, 2, 29)),
     (2026, 4, 31, date(2026, 4, 30)), (2026, 1, 15, date(2026, 1, 15))],
)  # fmt: skip
def test_clamp_day_uses_last_day_of_month(y: int, m: int, d: int, expected: date) -> None:
    assert clamp_day(y, m, d) == expected


@pytest.mark.parametrize(
    ("start", "value", "unit", "expected"),
    [(date(2026, 9, 20), 45, "days", date(2026, 11, 4)),
     (date(2026, 9, 20), 2, "weeks", date(2026, 10, 4)),
     (date(2026, 1, 31), 1, "months", date(2026, 2, 28)),
     (date(2026, 11, 30), 3, "months", date(2027, 2, 28)),
     (date(2026, 3, 31), -1, "months", date(2026, 2, 28))],
)  # fmt: skip
def test_add_interval_days_weeks_months(start: date, value: int, unit: str, expected: date) -> None:
    assert add_interval(start, value, unit) == expected


def test_add_interval_rejects_unknown_unit() -> None:
    with pytest.raises(ValueError):
        add_interval(date(2026, 1, 1), 1, "years")


# ---------------------------------------------------------------- invoice month


@pytest.mark.parametrize(
    ("purchase", "closing", "due", "month"),
    [
        (date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 10), "2026-09"),
        (date(2026, 9, 3), date(2026, 10, 3), date(2026, 10, 10), "2026-10"),
        (date(2026, 9, 20), date(2026, 10, 3), date(2026, 10, 10), "2026-10"),
    ],
)
def test_r1_2_invoice_month_closing_3_due_10(
    purchase: date, closing: date, due: date, month: str
) -> None:
    # docs/07#mês-de-fatura (closing 3, due 10)
    assert closing_after(CLOSE3_DUE10, purchase) == closing
    assert due_date_for_closing(closing, 3, 10) == due
    assert invoice_month(CLOSE3_DUE10, purchase) == month


def test_r1_2_invoice_month_closing_25_due_5_rolls_to_next_month() -> None:
    # docs/07#mês-de-fatura: 2026-09-10 -> closes 2026-09-25 -> due 2026-10-05 -> 2026-10
    purchase = date(2026, 9, 10)
    assert closing_after(CLOSE25_DUE5, purchase) == date(2026, 9, 25)
    assert due_date_for_closing(date(2026, 9, 25), 25, 5) == date(2026, 10, 5)
    assert invoice_month(CLOSE25_DUE5, purchase) == "2026-10"


def test_r1_2_invoice_month_year_turn() -> None:
    assert invoice_month(CLOSE25_DUE5, date(2026, 12, 26)) == "2027-02"
    assert invoice_month(CLOSE3_DUE10, date(2026, 12, 3)) == "2027-01"


def test_r1_2_closing_day_31_in_february_is_last_day() -> None:
    hist = billing(("2020-01", 31, 10))
    # Feb closing is clamped to 28; a purchase on the 28th goes to the March closing (31st).
    assert closing_after(hist, date(2026, 2, 27)) == date(2026, 2, 28)
    assert closing_after(hist, date(2026, 2, 28)) == date(2026, 3, 31)
    assert invoice_month(hist, date(2026, 2, 27)) == "2026-03"


def test_r1_1_billing_history_change_does_not_alter_previous_months() -> None:
    hist = billing(("2020-01", 3, 10), ("2026-11", 15, 22))
    # before the change: same as before
    assert invoice_month(hist, date(2026, 9, 20)) == "2026-10"
    # 2026-10-05 is after the Oct closing (3); next candidate is the Nov closing -> day 15
    assert closing_after(hist, date(2026, 10, 5)) == date(2026, 11, 15)
    assert invoice_month(hist, date(2026, 10, 5)) == "2026-11"
    assert invoice_month(hist, date(2026, 11, 10)) == "2026-11"
    assert invoice_month(hist, date(2026, 11, 15)) == "2026-12"


def test_billing_for_picks_greatest_from_month_and_first_before_any() -> None:
    hist = billing(("2026-11", 15, 22), ("2026-01", 3, 10))
    assert billing_for(hist, "2026-10").closing_day == 3
    assert billing_for(hist, "2026-11").closing_day == 15
    assert billing_for(hist, "2025-06").closing_day == 3  # before first version -> first


def test_billing_for_empty_history_raises() -> None:
    with pytest.raises(ValueError):
        billing_for([], "2026-01")


def test_actual_closing_date_from_pdf_takes_precedence() -> None:
    # docs/07: the real closing_date read from an imported invoice overrides the plan.
    actual = {"2026-10": date(2026, 10, 5)}  # bank closed on the 5th (holiday)
    assert invoice_month(CLOSE3_DUE10, date(2026, 10, 4)) == "2026-11"
    assert invoice_month(CLOSE3_DUE10, date(2026, 10, 4), actual) == "2026-10"


@pytest.mark.parametrize(
    ("today", "h"), [(date(2026, 10, 2), "2026-10"), (date(2026, 10, 3), "2026-11")]
)
def test_r1_3_current_invoice_month_h_on_closing_day(today: date, h: str) -> None:
    # docs/07#mês-corrente-de-um-cartão-h
    assert current_invoice_month(CLOSE3_DUE10, today) == h


def test_due_date_of_month() -> None:
    assert due_date_of_month(CLOSE3_DUE10, "2026-10") == date(2026, 10, 10)
    assert due_date_of_month(CLOSE25_DUE5, "2026-10") == date(2026, 10, 5)
