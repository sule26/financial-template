"""Subscriptions and interval-based recurring purchases (docs/07 "Assinaturas", docs/16)."""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal

from builders import Builders

from expense_tracker.domain.models import BillingEntry
from expense_tracker.domain.months import invoice_month
from expense_tracker.domain.recurrence import (
    end,
    months_between,
    occurrences,
    overdue,
    postpone,
    reanchor,
    recurring_charges,
    skip,
    subscription_charges,
    tolerance_days,
)

D = Decimal
mk = Builders
CLOSE3_DUE10 = [BillingEntry(from_month="2020-01", closing_day=3, due_day=10)]


def card_month(d: date) -> str:
    return invoice_month(CLOSE3_DUE10, d)


# ---------------------------------------------------------------- subscriptions (R1.4)


def test_r1_4_monthly_subscription_every_month_between_start_and_end() -> None:
    # docs/07#assinaturas
    sub = mk.subscription(amount="39.90", start="2026-10", end="2026-12")
    months = months_between("2026-09", "2027-01")
    got = subscription_charges(sub, months)
    assert [(c.month, c.amount) for c in got] == [
        ("2026-10", D("39.90")),
        ("2026-11", D("39.90")),
        ("2026-12", D("39.90")),
    ]
    assert all(c.source_id == "sub_1" and c.date is None for c in got)


def test_r1_4_monthly_subscription_without_end_runs_forever() -> None:
    sub = mk.subscription(start="2026-10")
    assert len(subscription_charges(sub, months_between("2026-10", "2036-09"))) == 120


def test_r1_4_annual_subscription_only_in_month_of_year_from_start() -> None:
    sub = mk.subscription(amount="199.00", start="2026-05", period="annual", month_of_year=3)
    got = subscription_charges(sub, months_between("2026-01", "2028-12"))
    assert [c.month for c in got] == ["2027-03", "2028-03"]


def test_r1_4_price_change_closes_old_and_opens_new_without_touching_past() -> None:
    old = mk.subscription("sub_old", "39.90", start="2026-01", end="2026-12")
    new = mk.subscription("sub_new", "44.90", start="2027-01")
    months = months_between("2026-11", "2027-02")
    charges = subscription_charges(old, months) + subscription_charges(new, months)
    assert {c.month: c.amount for c in charges} == {
        "2026-11": D("39.90"),
        "2026-12": D("39.90"),
        "2027-01": D("44.90"),
        "2027-02": D("44.90"),
    }


# ---------------------------------------------------------------- recurring purchases (R12)


RACAO = mk.recurring(last=date(2026, 9, 20), every=45)


def test_r12_2_recurring_occurrences_every_45_days() -> None:
    # docs/16#previsão: last purchase 2026-09-20, every 45 days, card closing 3 due 10
    dates = occurrences(RACAO, date(2027, 3, 31))
    assert dates == [date(2026, 11, 4), date(2026, 12, 19), date(2027, 2, 2), date(2027, 3, 19)]
    assert [card_month(d) for d in dates] == ["2026-12", "2027-01", "2027-02", "2027-04"]


def test_r12_2_recurring_charges_per_invoice_month_zero_one_or_two() -> None:
    # docs/16#previsão: invoices 2026-11 (0), 2026-12 (1), 2027-01 (1), 2027-02 (1),
    # 2027-03 (0), 2027-04 (1)
    months = months_between("2026-11", "2027-04")
    charges = recurring_charges(RACAO, months, card_month)
    per_month = Counter(c.month for c in charges)
    assert [per_month.get(m, 0) for m in months] == [0, 1, 1, 1, 0, 1]
    assert all(c.amount == D("250.00") and c.source_id == "rec_racao" for c in charges)
    assert charges[0].date == date(2026, 11, 4)


def test_r12_2_several_occurrences_in_the_same_invoice() -> None:
    weekly = mk.recurring(last=date(2026, 9, 20), every=2, unit="weeks")
    charges = recurring_charges(weekly, ["2026-10"], card_month)
    # 2026-09-20 + 14d = 10-04 (-> 2026-11); only 2026-09-20.. before closing 10-03: none.
    assert charges == []
    two = recurring_charges(weekly, ["2026-11"], card_month)
    assert [c.date for c in two] == [date(2026, 10, 4), date(2026, 10, 18), date(2026, 11, 1)]


def test_r12_2_recurring_charges_without_months_is_empty() -> None:
    assert recurring_charges(RACAO, [], card_month) == []


def test_r12_2_monthly_interval_keeps_day_clamped_to_month_end() -> None:
    rec = mk.recurring(last=date(2026, 1, 31), every=1, unit="months")
    got = occurrences(rec, date(2026, 4, 30))
    assert got[0] == date(2026, 2, 28)
    assert [d.month for d in got] == [2, 3, 4]


def test_r12_3_tolerance_is_ceil_of_interval_over_three() -> None:
    assert tolerance_days(RACAO) == 15
    assert tolerance_days(mk.recurring(every=10)) == 4
    assert tolerance_days(mk.recurring(every=1, unit="months")) == 10


def test_r12_3_reanchor_earlier_purchase_recomputes_next() -> None:
    # docs/16#reancoragem-r123: bought on 2026-10-30 (5 days early) -> next is 2026-12-14
    moved = reanchor(RACAO, date(2026, 10, 30))
    assert moved.last_date == date(2026, 10, 30)
    assert occurrences(moved, date(2027, 1, 31))[0] == date(2026, 12, 14)
    assert RACAO.last_date == date(2026, 9, 20)  # original untouched


def test_r12_3_reanchor_late_purchase_recomputes_next() -> None:
    moved = reanchor(RACAO, date(2026, 11, 15))
    assert occurrences(moved, date(2027, 1, 31))[0] == date(2026, 12, 30)


def test_r12_4_overdue_after_tolerance_without_purchase() -> None:
    # docs/16#ocorrência-que-não-aconteceu-r124: planned 2026-11-04, tolerance 15 days
    assert overdue(RACAO, date(2026, 11, 3)) is None  # not yet due
    assert overdue(RACAO, date(2026, 11, 19)) is None  # exactly at the tolerance
    assert overdue(RACAO, date(2026, 11, 20)) == date(2026, 11, 4)


def test_r12_4_postpone_new_date_becomes_next_occurrence() -> None:
    # "Adiar": the informed date becomes the anchor of the forecast
    later = postpone(RACAO, date(2026, 11, 25))
    assert occurrences(later, date(2027, 1, 31))[0] == date(2026, 11, 25)
    assert overdue(later, date(2026, 11, 26)) is None
    weekly = postpone(mk.recurring(every=2, unit="weeks"), date(2026, 11, 25))
    assert occurrences(weekly, date(2026, 12, 31))[0] == date(2026, 11, 25)
    monthly = postpone(mk.recurring(every=1, unit="months"), date(2026, 11, 25))
    assert occurrences(monthly, date(2026, 12, 31))[0] == date(2026, 11, 25)


def test_r12_4_postpone_monthly_to_month_end_keeps_informed_date() -> None:
    monthly = mk.recurring(last=date(2026, 1, 31), every=1, unit="months")
    later = postpone(monthly, date(2026, 3, 31))
    assert occurrences(later, date(2026, 5, 31)) == [date(2026, 3, 31), date(2026, 4, 30),
                                                     date(2026, 5, 31)]  # fmt: skip


def test_r12_2_monthly_on_31st_does_not_drift() -> None:
    # docs/16 "Previsão": months keep the day, clamped to month end (computed from the anchor)
    monthly = mk.recurring(last=date(2026, 1, 31), every=1, unit="months")
    assert occurrences(monthly, date(2026, 4, 30)) == [
        date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)
    ]  # fmt: skip


def test_r12_3_reanchor_clears_postponed_date() -> None:
    later = postpone(mk.recurring(last=date(2026, 1, 1), every=10), date(2026, 3, 1))
    assert reanchor(later, date(2026, 2, 20)).next_date is None


def test_r12_4_skip_next_is_planned_plus_interval() -> None:
    # "Pular": date goes to skipped_dates; next = planned + interval
    skipped = skip(RACAO, date(2026, 11, 4))
    assert skipped.skipped_dates == [date(2026, 11, 4)]
    assert occurrences(skipped, date(2027, 1, 31)) == [date(2026, 12, 19)]
    assert overdue(skipped, date(2026, 11, 25)) is None
    assert skip(skipped, date(2026, 11, 4)).skipped_dates == [date(2026, 11, 4)]  # idempotent


def test_r12_4_end_removes_from_projection() -> None:
    # "Encerrar": active = false; disappears from the projection
    ended = end(RACAO)
    assert ended.active is False
    assert occurrences(ended, date(2030, 1, 1)) == []
    assert recurring_charges(ended, months_between("2026-11", "2027-04"), card_month) == []
    assert overdue(ended, date(2030, 1, 1)) is None


def test_months_between_inclusive() -> None:
    assert months_between("2026-11", "2027-01") == ["2026-11", "2026-12", "2027-01"]
