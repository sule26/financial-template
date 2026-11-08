"""Regression tests for findings of the Phase 1 adversarial review."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from expense_tracker.domain.allocation import resolve_split
from expense_tracker.domain.investments import evolution
from expense_tracker.domain.ledger import DocumentInfo
from expense_tracker.domain.models import (
    BillingEntry,
    Category,
    IncomeEntry,
    Investment,
    Share,
    Snapshot,
    SplitProfile,
    SplitVersion,
    User,
)
from expense_tracker.domain.months import due_date_of_month


def test_r3_11_pending_candidate_does_not_hide_active_invoice(mk) -> None:  # type: ignore[no-untyped-def]
    # docs/05 "Substituição de fatura" step 1: calculations keep using A until B is approved
    card = mk.card("card_x")
    a = DocumentInfo(sha256="sha_a", kind="fatura", status="confirmed", card_id="card_x",
                     invoice_month="2026-09")  # fmt: skip
    b = DocumentInfo(sha256="sha_b", kind="fatura", status="pending_review", card_id="card_x",
                     invoice_month="2026-09", supersedes_candidate="faturas/a.pdf")  # fmt: skip
    tx_a = mk.tx("tx_a", 100, month="2026-09", day=date(2026, 8, 20), card="card_x", sha="sha_a")
    ledger = mk.ledger(date(2026, 10, 12), cards=[card], transactions=[tx_a], documents=[a, b])
    state, items = ledger.card_month("card_x", "2026-09")
    assert state == "real"
    assert [i.ref_id for i in items] == ["tx_a"]


@pytest.mark.parametrize("value", ["150.005", "33.335", "1.001"])
def test_r2_4_money_with_more_than_two_decimals_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError, match="2 decimal places"):
        Category(id="c", name="n", budget=value)  # type: ignore[arg-type]


def test_r6_12_proportional_share_rounding_to_zero_falls_back_to_fixed() -> None:
    users = {
        "a": User(
            id="a", name="A", income_history=[IncomeEntry(from_month="2026-01", amount="100000.00")]
        ),  # type: ignore[arg-type]
        "b": User(
            id="b", name="B", income_history=[IncomeEntry(from_month="2026-01", amount="4.00")]
        ),  # type: ignore[arg-type]
    }
    profile = SplitProfile(
        id="s", name="S", members=["a", "b"], mode="income_proportional",
        history=[SplitVersion(from_month="2026-01", shares=[
            Share(user_id="a", pct="60"), Share(user_id="b", pct="40")])],  # type: ignore[arg-type]
    )  # fmt: skip
    resolved = resolve_split(profile, "2026-05", users)
    assert [(s.user_id, s.pct) for s in resolved.shares] == [("a", D("60")), ("b", D("40"))]
    assert resolved.warnings


def test_billing_change_can_leave_a_month_without_invoice() -> None:
    # docs/07 "Mês de fatura": switching from closing 3/due 10 to 25/5 skips one invoice month
    history = [
        BillingEntry(from_month="2026-01", closing_day=3, due_day=10),
        BillingEntry(from_month="2026-11", closing_day=25, due_day=5),
    ]
    assert due_date_of_month(history, "2026-10") == date(2026, 10, 10)
    assert due_date_of_month(history, "2026-11") is None
    assert due_date_of_month(history, "2026-12") == date(2026, 12, 5)


def test_r9_5_evolution_ignores_closed_investment_after_closing() -> None:
    inv = Investment(
        id="i",
        name="CDB",
        owners=[Share(user_id="a", pct="100")],  # type: ignore[arg-type]
        snapshots=[Snapshot(date=date(2026, 9, 30), balance="1000.00")],  # type: ignore[arg-type]
        closed_at=date(2026, 10, 15),
    )
    months = dict((m, b) for m, b, _ in evolution([inv], ["2026-09", "2026-10", "2026-11"]))
    assert months == {"2026-09": D("1000.00"), "2026-10": D("0.00"), "2026-11": D("0.00")}
