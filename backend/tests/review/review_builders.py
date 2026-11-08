"""Builders for unit tests of ``expense_tracker.review`` (no I/O)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from expense_tracker.domain.models import (
    Account,
    Anticipation,
    BillingEntry,
    Card,
    InstallmentPlan,
    InstallmentRef,
    Interval,
    Investment,
    Kind,
    Origin,
    PaymentMethod,
    RecurringPurchase,
    ReviewInfo,
    Share,
    Source,
    Subscription,
    Transaction,
    User,
)
from expense_tracker.review.reconcile import InvoiceDoc, ReconContext

ME = "u_me"
ANA = "u_ana"
PAI = "u_pai"


def owners(*pairs: tuple[str, str]) -> list[Share]:
    return [Share(user_id=u, pct=Decimal(p)) for u, p in pairs]


def card(cid: str = "card_a", parent: str | None = None, digits: list[str] | None = None) -> Card:
    if parent:
        return Card(id=cid, name=cid, parent_card_id=parent, last_digits=digits or [])
    return Card(
        id=cid,
        name=cid,
        owners=owners((ME, "100")),
        responsible_user_id=ME,
        last_digits=digits or [],
        billing_history=[BillingEntry(from_month="2026-01", closing_day=5, due_day=15)],
    )


def account(aid: str = "acc_a", responsible: str = ME) -> Account:
    return Account(id=aid, name=aid, owners=owners((ME, "100")), responsible_user_id=responsible)


_SEQ = [0]


def line(
    desc: str,
    amount: str,
    *,
    day: date = date(2026, 9, 10),
    month: str = "2026-10",
    card_id: str | None = "card_a",
    account_id: str | None = None,
    n: int | None = None,
    of: int | None = None,
    kind: Kind | None = None,
    tag: str | None = None,
    method: PaymentMethod | None = None,
    source: str = "import",
    provisional: bool = False,
    sha: str = "sha_doc",
    tid: str | None = None,
    **extra: Any,
) -> Transaction:
    _SEQ[0] += 1
    value = Decimal(amount)
    if kind is None:
        kind = Kind.REFUND if value < 0 else Kind.EXPENSE
    if method is None:
        method = PaymentMethod.CREDIT if card_id else PaymentMethod.DEBIT
    return Transaction(
        id=tid or f"tx_{_SEQ[0]}",
        fingerprint=None if source == "manual" else f"fp_{tid or _SEQ[0]}",
        kind=kind,
        source=Source(type=source, sha256=sha if source == "import" else None),  # type: ignore[arg-type]
        provisional=provisional,
        payment_method=method,
        card_id=card_id,
        account_id=account_id,
        purchase_date=day,
        invoice_month=month,
        description=desc,
        amount=value,
        installment=InstallmentRef(n=n, of=of) if n and of else None,
        tag=tag,
        review=ReviewInfo() if source == "import" else None,
        **extra,
    )


def plan(
    pid: str = "plan_a",
    desc: str = "LOJA X",
    of: int = 10,
    first: str = "2026-08",
    installment: str = "50.00",
    card_id: str = "card_a",
    anticipation: Anticipation | None = None,
    **extra: Any,
) -> InstallmentPlan:
    amt = Decimal(installment)
    return InstallmentPlan(
        id=pid,
        origin=extra.pop("origin", Origin()),
        card_id=card_id,
        description=desc,
        total_installments=of,
        first_invoice_month=first,
        total_amount=amt * of,
        installment_amount=amt,
        anticipation=anticipation,
        **extra,
    )


def subscription(
    sid: str = "sub_a", desc: str = "STREAMING", amount: str = "40.00", **kw: Any
) -> Subscription:
    kw.setdefault("card_id", "card_a")
    return Subscription(
        id=sid, description=desc, amount=Decimal(amount), start_month="2026-01", **kw
    )


def recurring(
    rid: str = "rec_a",
    desc: str = "RACAO PET",
    amount: str = "200.00",
    every: int = 45,
    last: date = date(2026, 8, 1),
    **kw: Any,
) -> RecurringPurchase:
    kw.setdefault("card_id", "card_a")
    return RecurringPurchase(
        id=rid,
        description=desc,
        estimated_amount=Decimal(amount),
        every=Interval(value=every),
        last_date=last,
        **kw,
    )


def investment(iid: str = "inv_a", account_id: str | None = None, **kw: Any) -> Investment:
    return Investment(id=iid, name=iid, owners=owners((ME, "100")), account_id=account_id, **kw)


def invoice_doc(
    path: str = "faturas/a.pdf",
    card_id: str = "card_a",
    month: str = "2026-09",
    total: str | None = "500.00",
    amount_due: str | None = "500.00",
    due: date | None = date(2026, 9, 15),
    closing: date | None = date(2026, 9, 5),
) -> InvoiceDoc:
    return InvoiceDoc(
        path,
        f"sha_{path}",
        card_id,
        month,
        Decimal(total) if total is not None else None,
        Decimal(amount_due) if amount_due is not None else None,
        due,
        closing,
    )


def ctx(**kw: Any) -> ReconContext:
    cards = kw.pop("cards", [card()])
    accounts = kw.pop("accounts", [account()])
    users = kw.pop(
        "users",
        [
            User(id=ME, name="Eu"),
            User(id=ANA, name="Ana"),
            User(id=PAI, name="Pai", aliases=["JOSE DA SILVA"]),
        ],
    )
    base: dict[str, Any] = {
        "cards": {c.id: c for c in cards},
        "accounts": {a.id: a for a in accounts},
        "users": {u.id: u for u in users},
        "plans": [],
        "subscriptions": [],
        "recurring": [],
        "investments": [],
        "manuals": [],
        "invoices": [],
        "other_lines": [],
    }
    base.update(kw)
    return ReconContext(**base)


def types(result: Any, tx: Transaction) -> list[str]:
    return [s.type for s in result.suggestions.get(tx.id, [])]


def only(result: Any, tx: Transaction) -> Any:
    found = result.suggestions.get(tx.id, [])
    assert len(found) == 1, found
    return found[0]
