"""Domain model validation (docs/04 "Invariantes" and field rules)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from expense_tracker.domain.models import (
    Account,
    Card,
    IncomeEntry,
    InstallmentPlan,
    InstallmentRef,
    Interval,
    Movement,
    RecurringPurchase,
    Settlement,
    Share,
    SplitProfile,
    Subscription,
    Transaction,
    check_allocation,
    validate_shares,
)

D = Decimal


def s(user: str, pct: str) -> Share:
    return Share(user_id=user, pct=D(pct))


# ---------------------------------------------------------------- allocations (invariant 1)


@pytest.mark.parametrize("pct", ["0", "-1", "100.01"])
def test_r6_2_share_pct_must_be_in_0_100(pct: str) -> None:
    with pytest.raises(ValidationError):
        Share(user_id="u", pct=D(pct))


def test_r6_2_fixed_allocation_must_sum_exactly_100() -> None:
    assert validate_shares([s("a", "33.34"), s("b", "33.33"), s("c", "33.33")])
    with pytest.raises(ValueError, match=r"sum to 100\.00"):
        validate_shares([s("a", "50.00"), s("b", "49.99")])


def test_fixed_allocation_rejects_empty_and_duplicated_users() -> None:
    with pytest.raises(ValueError, match="at least one"):
        validate_shares([])
    with pytest.raises(ValueError, match="duplicated"):
        validate_shares([s("a", "50"), s("a", "50")])


def test_check_allocation_accepts_split_ref_and_none() -> None:
    from expense_tracker.domain.models import SplitRef

    ref = SplitRef(split_id="split_casal")
    assert check_allocation(ref) is ref
    assert check_allocation(None) is None


def test_floats_are_rejected_in_models() -> None:
    # docs/04 invariant 4
    with pytest.raises(ValidationError):
        Share(user_id="u", pct=50.0)  # type: ignore[arg-type]


def test_account_owners_are_validated() -> None:
    with pytest.raises(ValidationError):
        Account(id="a", name="A", owners=[s("u", "60")], responsible_user_id="u")


# ---------------------------------------------------------------- people and splits


def test_r1_5_income_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        IncomeEntry(from_month="2026-01", amount=D("-1"))
    assert IncomeEntry(from_month="2026-01", amount=D("0")).amount == D("0.00")


def _profile(**kw: Any) -> SplitProfile:
    data: dict[str, Any] = {
        "id": "split_casal",
        "name": "Casal",
        "members": ["a", "b"],
        "history": [{"from_month": "2026-01", "shares": [s("a", "60"), s("b", "40")]}],
    }
    data.update(kw)
    return SplitProfile.model_validate(data)


def test_r6_10_split_profile_valid() -> None:
    assert _profile().mode == "fixed"


def test_split_profile_members_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        _profile(members=["a", "a", "b"])


def test_split_version_cannot_reference_non_member() -> None:
    with pytest.raises(ValidationError, match="not a member"):
        _profile(members=["a", "c"])


def test_split_versions_must_have_distinct_months() -> None:
    v = {"from_month": "2026-01", "shares": [s("a", "60"), s("b", "40")]}
    with pytest.raises(ValidationError, match="distinct"):
        _profile(history=[v, v])


def test_split_version_shares_must_sum_100() -> None:
    with pytest.raises(ValidationError):
        _profile(history=[{"from_month": "2026-01", "shares": [s("a", "60"), s("b", "30")]}])


# ---------------------------------------------------------------- cards


def test_r1_1_main_card_needs_billing_history() -> None:
    with pytest.raises(ValidationError, match="billing_history"):
        Card(id="c", name="C")
    # an additional card bills on the main card and needs none
    assert Card(id="c2", name="C2", parent_card_id="c").billing_history == []


def test_card_last_digits_pattern() -> None:
    with pytest.raises(ValidationError):
        Card(id="c", name="C", parent_card_id="p", last_digits=["12a4"])


# ---------------------------------------------------------------- transactions


def _tx(**kw: Any) -> Transaction:
    data: dict[str, Any] = {
        "id": "tx",
        "source": {"type": "manual"},
        "purchase_date": date(2026, 9, 1),
        "invoice_month": "2026-09",
        "description": "X",
        "amount": "10.00",
        "card_id": "c",
    }
    data.update(kw)
    return Transaction.model_validate(data)


def test_credit_transaction_needs_card() -> None:
    with pytest.raises(ValidationError, match="card_id"):
        _tx(card_id=None)


def test_non_credit_transaction_needs_account() -> None:
    with pytest.raises(ValidationError, match="account_id"):
        _tx(payment_method="pix", card_id=None)
    assert _tx(payment_method="pix", card_id=None, account_id="acc").account_id == "acc"


def test_transaction_money_serializes_as_canonical_string() -> None:
    dumped = _tx(amount="-65").model_dump(mode="json")
    assert dumped["amount"] == "-65.00"


def test_transaction_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _tx(foo=1)


def test_installment_ref_n_cannot_exceed_of() -> None:
    with pytest.raises(ValidationError):
        InstallmentRef(n=4, of=3)
    assert InstallmentRef(n=3, of=3).n == 3


# ---------------------------------------------------------------- plans, subscriptions, recurring


def _plan(**kw: Any) -> InstallmentPlan:
    data: dict[str, Any] = {
        "id": "p",
        "card_id": "c",
        "description": "LOJA",
        "total_installments": 3,
        "first_invoice_month": "2026-08",
        "total_amount": "300.00",
    }
    data.update(kw)
    return InstallmentPlan.model_validate(data)


def test_plan_anticipation_and_cancellation_ranges() -> None:
    with pytest.raises(ValidationError, match="anticipation"):
        _plan(anticipation={"from_n": 4, "target_month": "2026-09"})
    with pytest.raises(ValidationError, match="status_override"):
        _plan(status_override={"from_n": 4})
    assert _plan(anticipation={"from_n": 3, "target_month": "2026-09"}).anticipation


def _sub(**kw: Any) -> Subscription:
    data: dict[str, Any] = {
        "id": "sub",
        "description": "STREAM",
        "amount": "50.00",
        "card_id": "c",
        "start_month": "2026-01",
    }
    data.update(kw)
    return Subscription.model_validate(data)


def test_r1_4_subscription_validation() -> None:
    with pytest.raises(ValidationError, match="month_of_year"):
        _sub(period="annual")
    with pytest.raises(ValidationError, match="end_month"):
        _sub(end_month="2025-12")
    with pytest.raises(ValidationError, match="card_id or account_id"):
        _sub(card_id=None)
    assert _sub(period="annual", month_of_year=3).month_of_year == 3


@pytest.mark.parametrize(("value", "unit", "days"), [(45, "days", 45), (2, "weeks", 14),
                                                      (1, "months", 30)])  # fmt: skip
def test_r12_1_interval_days(value: int, unit: str, days: int) -> None:
    assert Interval(value=value, unit=unit).days == days  # type: ignore[arg-type]


def test_r12_1_recurring_needs_card_or_account() -> None:
    with pytest.raises(ValidationError):
        RecurringPurchase.model_validate(
            {
                "id": "r",
                "description": "R",
                "estimated_amount": "1.00",
                "every": {"value": 1},
                "last_date": date(2026, 1, 1),
            }
        )


# ---------------------------------------------------------------- settlements and investments


def test_r6_4_settlement_must_be_between_distinct_users_and_positive() -> None:
    base: dict[str, Any] = {
        "id": "s",
        "from_user_id": "a",
        "to_user_id": "b",
        "amount": "10",
        "date": date(2026, 1, 1),
        "month": "2026-01",
    }
    assert Settlement.model_validate(base).amount == D("10.00")
    with pytest.raises(ValidationError, match="differ"):
        Settlement.model_validate({**base, "to_user_id": "a"})
    with pytest.raises(ValidationError, match="positive"):
        Settlement.model_validate({**base, "amount": "0"})


def test_r9_3_movement_amount_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Movement(date=date(2026, 1, 1), type="contribution", amount=D("0"))
