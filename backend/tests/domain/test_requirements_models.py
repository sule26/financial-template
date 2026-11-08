"""Requirement coverage for model-level rules not covered elsewhere (trace gate)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from expense_tracker.domain.models import (
    ACCOUNT_METHODS,
    Investment,
    PaymentMethod,
    Share,
    Source,
    Transaction,
    User,
)


def test_r6_1_user_income_is_optional() -> None:
    user = User(id="usr_pais", name="Pais")
    assert user.income_history == []
    with pytest.raises(ValidationError):
        User(id="x", name="")


def test_r11_1_all_payment_methods_supported() -> None:
    assert {m.value for m in PaymentMethod} == {
        "credit", "benefit", "debit", "pix", "transfer", "boleto", "cash",
    }  # fmt: skip


def test_r11_3_account_methods_need_account_and_credit_needs_card() -> None:
    assert ACCOUNT_METHODS["checking"] == {
        PaymentMethod.DEBIT, PaymentMethod.PIX, PaymentMethod.TRANSFER, PaymentMethod.BOLETO,
    }  # fmt: skip
    base = {"id": "t", "source": Source(type="manual"), "purchase_date": date(2026, 10, 1),
            "invoice_month": "2026-10", "description": "X", "amount": "10.00"}  # fmt: skip
    with pytest.raises(ValidationError, match="account_id"):
        Transaction(**base, payment_method=PaymentMethod.PIX)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="card_id"):
        Transaction(**base, payment_method=PaymentMethod.CREDIT)  # type: ignore[arg-type]
    ok = Transaction(**base, payment_method=PaymentMethod.PIX, account_id="acc")  # type: ignore[arg-type]
    assert ok.account_id == "acc"


def test_r9_1_investment_fields_and_owners_validated() -> None:
    inv = Investment(id="i", name="Tesouro", institution="X", type="fixed_income",
                     owners=[Share(user_id="eu", pct="100")], goal_id="g")  # type: ignore[arg-type]  # fmt: skip
    assert inv.type == "fixed_income"
    with pytest.raises(ValidationError):
        Investment(id="i", name="X", owners=[Share(user_id="eu", pct="50")])  # type: ignore[arg-type]
