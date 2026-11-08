"""R14.4: several named incomes per user and one-off incomes of a single month."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from builders import ANA, EU, Builders
from pydantic import ValidationError

from expense_tracker.domain.allocation import income_for, resolve_split
from expense_tracker.domain.models import (
    IncomeEntry,
    IncomeSource,
    OneOffIncome,
    SplitProfile,
    SplitVersion,
    User,
)
from expense_tracker.domain.reports import committed_income

D = Decimal
mk = Builders


def _user(uid: str = EU, **kw: object) -> User:
    return User(id=uid, name=uid, **kw)  # type: ignore[arg-type]


def _src(name: str, *entries: tuple[str, str]) -> IncomeSource:
    return IncomeSource(
        name=name, history=[IncomeEntry(from_month=m, amount=D(a)) for m, a in entries]
    )


def test_r14_4_income_is_the_sum_of_every_named_source() -> None:
    user = _user(
        incomes=[
            _src("Emprego A", ("2026-01", "6000")),
            _src("Freela", ("2026-03", "1500"), ("2026-08", "0")),  # stopped in August
        ]
    )
    assert income_for(user, "2026-02") == D("6000")
    assert income_for(user, "2026-05") == D("7500")
    assert income_for(user, "2026-09") == D("6000")


def test_r14_4_legacy_history_still_counts_with_the_sources() -> None:
    user = _user(
        income_history=[IncomeEntry(from_month="2026-01", amount=D("3000"))],
        incomes=[_src("Emprego B", ("2026-01", "2000"))],
    )
    assert income_for(user, "2026-06") == D("5000")


def test_r14_4_one_off_income_counts_only_in_its_month() -> None:
    user = _user(
        incomes=[_src("Emprego", ("2026-01", "5000"))],
        one_off_incomes=[OneOffIncome(month="2026-12", amount=D("2500"), description="Bônus")],
    )
    assert income_for(user, "2026-11") == D("5000")
    assert income_for(user, "2026-12") == D("7500")
    assert income_for(user, "2027-01") == D("5000")


def test_r14_4_only_one_off_income_still_is_income_that_month() -> None:
    user = _user(one_off_incomes=[OneOffIncome(month="2026-12", amount=D("800"))])
    assert income_for(user, "2026-11") is None
    assert income_for(user, "2026-12") == D("800")


def test_r14_4_one_off_income_does_not_change_the_proportional_split() -> None:
    eu = _user(
        EU,
        incomes=[_src("Emprego", ("2026-01", "6000"))],
        one_off_incomes=[OneOffIncome(month="2026-12", amount=D("6000"))],
    )
    ana = _user(ANA, incomes=[_src("Emprego", ("2026-01", "4000"))])
    profile = SplitProfile(
        id="split_casal",
        name="Casal",
        members=[EU, ANA],
        mode="income_proportional",
        history=[SplitVersion(from_month="2026-01")],
    )
    shares = resolve_split(profile, "2026-12", {EU: eu, ANA: ana}).shares
    assert [(s.user_id, s.pct) for s in shares] == [(EU, D("60.00")), (ANA, D("40.00"))]


def test_r14_4_one_off_income_enters_committed_income() -> None:
    card = mk.card("card_eu", owners=mk.shares((EU, 100)), responsible=EU)
    plan = mk.plan("plan_x", n=1, total=1000, first="2026-12", card="card_eu")
    eu = _user(
        EU,
        incomes=[_src("Emprego", ("2026-01", "4000"))],
        one_off_incomes=[OneOffIncome(month="2026-12", amount=D("1000"))],
    )
    ledger = mk.ledger(date(2026, 10, 12), cards=[card], plans=[plan], users=[eu])
    (c,) = committed_income(ledger, [ledger.month("2026-12")], eu)
    assert (c.income, c.ratio) == (D("5000"), D("20.00"))


def test_r14_4_validation() -> None:
    with pytest.raises(ValidationError):
        OneOffIncome(month="2026-12", amount=D("0"))
    with pytest.raises(ValidationError):
        IncomeSource(name="", history=[])
    with pytest.raises(ValidationError):
        _src("Dup", ("2026-01", "1"), ("2026-01", "2"))
    assert OneOffIncome(month="2026-12", amount=D("1")).description == "Renda extra"
