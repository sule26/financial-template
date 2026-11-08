"""Months and invoice-month rules (docs/07 "Mês de fatura" and "Mês corrente de um cartão").

A month is a ``"YYYY-MM"`` string. Functions here are pure; "today" is always a parameter.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from typing import Annotated, Protocol

from pydantic import AfterValidator

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _check_month(value: str) -> str:
    if not MONTH_RE.match(value):
        raise ValueError(f"month must be YYYY-MM, got {value!r}")
    return value


Month = Annotated[str, AfterValidator(_check_month)]


def month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def parse_month(month: str) -> tuple[int, int]:
    _check_month(month)
    return int(month[:4]), int(month[5:])


def add_months(month: str, delta: int) -> str:
    year, mon = parse_month(month)
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_diff(a: str, b: str) -> int:
    """Number of months from ``b`` to ``a`` (``a - b``)."""
    ya, ma = parse_month(a)
    yb, mb = parse_month(b)
    return (ya - yb) * 12 + (ma - mb)


def month_range(start: str, count: int) -> list[str]:
    return [add_months(start, i) for i in range(count)]


def clamp_day(year: int, month: int, day: int) -> date:
    """Day in month, clamped to the last day (31 in February -> 28/29)."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def add_interval(d: date, value: int, unit: str) -> date:
    """Add days, weeks or months (months keep the day, clamped to month end)."""
    if unit == "days":
        return d + timedelta(days=value)
    if unit == "weeks":
        return d + timedelta(weeks=value)
    if unit == "months":
        y, m = parse_month(add_months(month_of(d), value))
        return clamp_day(y, m, d.day)
    raise ValueError(f"unknown interval unit {unit!r}")


class BillingPeriod(Protocol):
    @property
    def from_month(self) -> str: ...

    @property
    def closing_day(self) -> int: ...

    @property
    def due_day(self) -> int: ...


def billing_for(history: Sequence[BillingPeriod], closing_month: str) -> BillingPeriod:
    """Billing entry in force for a closing month (greatest ``from_month <= month``)."""
    if not history:
        raise ValueError("billing history is empty")
    ordered = sorted(history, key=lambda b: b.from_month)
    chosen = ordered[0]
    for entry in ordered:
        if entry.from_month <= closing_month:
            chosen = entry
    return chosen


def due_date_for_closing(closing: date, closing_day: int, due_day: int) -> date:
    """Due date for a closing date: same month if ``due_day > closing_day``, else next month."""
    if due_day > closing_day:
        return clamp_day(closing.year, closing.month, due_day)
    y, m = parse_month(add_months(month_of(closing), 1))
    return clamp_day(y, m, due_day)


def _closings_from(history: Sequence[BillingPeriod], start: date) -> Iterator[date]:
    month = add_months(month_of(start), -1)
    while True:
        y, m = parse_month(month)
        yield clamp_day(y, m, billing_for(history, month).closing_day)
        month = add_months(month, 1)


def closing_after(
    history: Sequence[BillingPeriod],
    d: date,
    actual_closings: dict[str, date] | None = None,
) -> date:
    """First closing date strictly after ``d`` (purchase on closing day goes to the next invoice).

    ``actual_closings`` maps a closing month to the real closing date read from an imported
    invoice; it takes precedence over the billing history for that month.
    """
    actual = actual_closings or {}
    for planned in _closings_from(history, d):
        closing = actual.get(month_of(planned), planned)
        if closing > d:
            return closing
    raise AssertionError("unreachable")  # pragma: no cover


def invoice_month(
    history: Sequence[BillingPeriod],
    purchase: date,
    actual_closings: dict[str, date] | None = None,
) -> str:
    """Invoice month (month of the due date) for a purchase on ``purchase``.

    docs/07 examples (closing 3, due 10): 2026-09-02 -> 2026-09; 2026-09-03 -> 2026-10.
    """
    closing = closing_after(history, purchase, actual_closings)
    entry = billing_for(history, month_of(closing))
    return month_of(due_date_for_closing(closing, entry.closing_day, entry.due_day))


def current_invoice_month(history: Sequence[BillingPeriod], today: date) -> str:
    """``H(card)``: invoice month of the invoice that is still open today."""
    return invoice_month(history, today)


def due_date_of_month(history: Sequence[BillingPeriod], month: str) -> date | None:
    """Planned due date of the invoice whose invoice month is ``month``.

    ``None`` when no invoice is due in that month, which happens once when the billing history
    changes the closing/due days (docs/07 "Mês de fatura": the change may skip one month).
    """
    for delta in (0, -1):
        closing_month = add_months(month, delta)
        entry = billing_for(history, closing_month)
        y, m = parse_month(closing_month)
        closing = clamp_day(y, m, entry.closing_day)
        due = due_date_for_closing(closing, entry.closing_day, entry.due_day)
        if month_of(due) == month:
            return due
    return None
