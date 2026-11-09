"""Subscriptions and interval-based recurring purchases (docs/07 "Assinaturas", docs/16)."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from expense_tracker.domain.models import Pause, RecurringPurchase, Subscription
from expense_tracker.domain.months import (
    add_interval,
    add_months,
    clamp_day,
    month_diff,
    month_of,
    month_range,
    parse_month,
)


@dataclass(frozen=True)
class PlannedCharge:
    source_id: str
    month: str
    amount: Decimal
    date: date | None = None


def subscription_charges(sub: Subscription, months: list[str]) -> list[PlannedCharge]:
    """Monthly: every month in [start, end]; annual: only ``month_of_year`` (R1.4)."""
    out: list[PlannedCharge] = []
    for month in months:
        if month < sub.start_month or (sub.end_month is not None and month > sub.end_month):
            continue
        if sub.period == "annual" and parse_month(month)[1] != sub.month_of_year:
            continue
        if sub.paused_in(month):  # R14.11
            continue
        out.append(PlannedCharge(sub.id, month, sub.amount_in(month)))
    return out


def tolerance_days(rec: RecurringPurchase) -> int:
    """±⌈interval/3⌉ days (R12.3)."""
    return -(-rec.every.days // 3)


def occurrences(rec: RecurringPurchase, until: date) -> list[date]:
    """Next planned dates up to ``until`` (R12.2), skipping skipped dates.

    Dates are computed from the anchor (``k × interval``), so a monthly purchase on the 31st
    stays on the last day of shorter months instead of drifting. ``next_date`` (set by
    "adiar") replaces the first occurrence and becomes the new anchor.
    """
    if not rec.active:
        return []
    anchor = rec.last_date
    out: list[date] = []
    k = 1
    if rec.next_date is not None:
        anchor = rec.next_date
        k = 0
    for _ in range(2000):
        current = add_interval(anchor, k * rec.every.value, rec.every.unit)
        if k > 0:  # a postponed date (k = 0) is kept as informed, only the next ones go to day X
            current = _on_day(rec, current)
        k += 1
        if current > until:
            break
        if current in rec.skipped_dates or rec.paused_in(month_of(current)):  # R14.11
            continue
        out.append(current)
    return out


def recurring_charges(
    rec: RecurringPurchase,
    months: list[str],
    month_for_date: Callable[[date], str],
) -> list[PlannedCharge]:
    """Planned charges of a recurring purchase whose invoice month falls in ``months``."""
    if not months:
        return []
    last_month = max(months)
    y, m = parse_month(last_month)
    until = date(y, m, 28) + timedelta(days=45)
    wanted = set(months)
    return [
        PlannedCharge(rec.id, month_for_date(d), rec.amount_in(month_of(d)), d)
        for d in occurrences(rec, until)
        if month_for_date(d) in wanted
    ]


def _unpaid(rec: RecurringPurchase, dates: list[date], paid: Collection[str]) -> list[date]:
    """R14.26: a bill's due dates in months already paid are not pending any more."""
    return [d for d in dates if month_of(d) not in paid]


def bill_month(rec: RecurringPurchase, paid_on: date) -> str:
    """R14.26: month of the bill a payment on ``paid_on`` settles: the nearest due date."""
    horizon = paid_on + timedelta(days=2 * rec.every.days)
    dates = [rec.last_date, *occurrences(rec.model_copy(update={"active": True}), horizon)]
    return month_of(min(dates, key=lambda d: (abs((d - paid_on).days), d)))


def overdue(rec: RecurringPurchase, today: date, paid: Collection[str] = ()) -> date | None:
    """First planned date already beyond tolerance with no purchase (R12.4), if any.

    ``paid``: months of a household bill already paid (they never move the schedule).
    """
    upcoming = _unpaid(rec, occurrences(rec, today), paid)
    if upcoming and (today - upcoming[0]).days > tolerance_days(rec):
        return upcoming[0]
    return None


def _on_day(rec: RecurringPurchase, d: date) -> date:
    """R14.30: with ``day_of_month``, the date moves to that day of its month."""
    if rec.day_of_month is None:
        return d
    return clamp_day(d.year, d.month, rec.day_of_month)


def reanchor(rec: RecurringPurchase, real_date: date) -> RecurringPurchase:
    """R12.3: the real purchase date becomes the new anchor.

    R14.30: with ``day_of_month`` the anchor is the planned day X nearest to the real date, so
    a purchase a few days early or late does not move the following ones off day X.
    """
    anchor = real_date
    if rec.day_of_month is not None:
        month = month_of(real_date)
        candidates = [_on_day(rec, date(*parse_month(add_months(month, k)), 1)) for k in (-1, 0, 1)]
        anchor = min(candidates, key=lambda d: (abs((d - real_date).days), d))
    return rec.model_copy(update={"last_date": anchor, "next_date": None})


def postpone(rec: RecurringPurchase, new_date: date) -> RecurringPurchase:
    """Adiar (R12.4): the informed date is the next expected purchase."""
    return rec.model_copy(update={"next_date": new_date})


def skip(rec: RecurringPurchase, planned: date) -> RecurringPurchase:
    return rec.model_copy(update={"skipped_dates": sorted({*rec.skipped_dates, planned})})


def end(
    rec: RecurringPurchase, today: date | None = None, paid: Collection[str] = ()
) -> RecurringPurchase:
    """Desativar (R14.11): opens a pause from this month on, keeping the history.

    Without ``today`` (legacy call) it only switches the purchase off.
    """
    if today is None:
        return rec.model_copy(update={"active": False})
    # From the first purchase that did not happen yet (an overdue one included), else today.
    pending = _unpaid(rec, occurrences(rec, today), paid)
    month = month_of(pending[0]) if pending else month_of(today)
    if rec.group == "household":
        # a bill: past months keep their state (paid or late), R14.27 "meses anteriores não mudam"
        month = max(month, month_of(today))
    if rec.paused_in(month):
        return rec
    return rec.model_copy(update={"pauses": [*rec.pauses, Pause(from_month=month)]})


def resume(
    rec: RecurringPurchase, next_date: date | None = None, today: date | None = None
) -> RecurringPurchase:
    """Ativar de novo (R14.11): closes the open pause the month before it comes back;
    forecasts return from ``next_date`` when given, else from the anchor."""
    back = next_date or today
    pauses = list(rec.pauses)
    if back is not None:
        back_month = month_of(back)
        closed: list[Pause] = []
        for p in pauses:
            if p.until_month is None:
                if back_month <= p.from_month:
                    continue  # paused and resumed before it took effect: drop it
                p = p.model_copy(update={"until_month": add_months(back_month, -1)})
            closed.append(p)
        pauses = closed
    return rec.model_copy(
        update={"active": True, "next_date": next_date or rec.next_date, "pauses": pauses}
    )


def months_between(start: str, end_month: str) -> list[str]:
    return month_range(start, month_diff(end_month, start) + 1)
