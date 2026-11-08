"""R14.6: without a selected person the summary uses the household income (sum of everyone)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from builders import ANA, EU, PAIS, Builders

from expense_tracker.domain.reports import summarize

D = Decimal
mk = Builders
TODAY = date(2026, 10, 12)


def _ledger(users: list) -> object:  # type: ignore[type-arg]
    card = mk.card("card_eu", owners=mk.shares((EU, 100)), responsible=EU)
    return mk.ledger(TODAY, cards=[card], users=users)


def test_r14_6_household_income_is_the_sum_of_every_user() -> None:
    users = [
        mk.user(EU, income=[("2026-01", "8000")]),
        mk.user(ANA, income=[("2026-01", "6000")]),
        mk.user(PAIS),  # no income: does not count and does not hide the others
    ]
    ledger = _ledger(users)
    s = summarize(ledger, ledger.month("2026-10"))  # type: ignore[attr-defined, arg-type]
    assert s.income == D("14000.00")


def test_r14_6_household_income_follows_each_users_history() -> None:
    users = [
        mk.user(EU, income=[("2026-01", "8000"), ("2026-10", "9000")]),
        mk.user(ANA, income=[("2026-01", "6000")]),
    ]
    ledger = _ledger(users)
    sep = summarize(ledger, ledger.month("2026-09"))  # type: ignore[attr-defined, arg-type]
    oct_ = summarize(ledger, ledger.month("2026-10"))  # type: ignore[attr-defined, arg-type]
    assert (sep.income, oct_.income) == (D("14000.00"), D("15000.00"))


def test_r14_6_household_income_is_none_when_nobody_has_income() -> None:
    ledger = _ledger([mk.user(EU), mk.user(ANA)])
    s = summarize(ledger, ledger.month("2026-10"))  # type: ignore[attr-defined, arg-type]
    assert (s.income, s.benefit_income) == (None, None)


def test_r14_6_selected_person_keeps_only_their_income() -> None:
    users = [mk.user(EU, income=[("2026-01", "8000")]), mk.user(ANA, income=[("2026-01", "6000")])]
    ledger = _ledger(users)
    s = summarize(ledger, ledger.month("2026-10"), users[1])  # type: ignore[attr-defined, arg-type]
    assert s.income == D("6000.00")
