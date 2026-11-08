"""Builders for domain tests (re-exported as fixtures by conftest.py).

Every builder returns a validated domain model with sensible defaults so that each test only
spells out what matters for the rule under test. Exposed through the ``mk`` fixture
(session-scoped so it can also be used inside hypothesis tests); tests may also
import ``Builders`` directly for module-level constants.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from expense_tracker.domain.ledger import DocumentInfo, Ledger, LedgerState
from expense_tracker.domain.models import (
    Account,
    Allocation,
    BillingEntry,
    Card,
    IncomeEntry,
    InstallmentPlan,
    Investment,
    Kind,
    Movement,
    PaymentMethod,
    RecurringPurchase,
    Rule,
    Settlement,
    Share,
    Snapshot,
    Source,
    SplitProfile,
    SplitRef,
    SplitVersion,
    Subscription,
    Transaction,
    User,
)

EU = "usr_eu"
ANA = "usr_ana"
PAIS = "usr_pais"


def D(value: str | int) -> Decimal:
    return Decimal(str(value))


class Builders:
    """Factory helpers (static) for domain models."""

    EU = EU
    ANA = ANA
    PAIS = PAIS

    # ------------------------------------------------------------ people and splits

    @staticmethod
    def shares(*pairs: tuple[str, str | int]) -> list[Share]:
        return [Share(user_id=u, pct=D(p)) for u, p in pairs]

    @staticmethod
    def user(
        uid: str,
        name: str | None = None,
        income: Iterable[tuple[str, str | int]] = (),
        benefit: Iterable[tuple[str, str | int]] = (),
    ) -> User:
        return User(
            id=uid,
            name=name or uid.removeprefix("usr_").capitalize(),
            income_history=[IncomeEntry(from_month=m, amount=D(a)) for m, a in income],
            benefit_income_history=[IncomeEntry(from_month=m, amount=D(a)) for m, a in benefit],
        )

    @staticmethod
    def split(
        sid: str,
        versions: Sequence[tuple[str, Sequence[tuple[str, str | int]]]],
        mode: str = "fixed",
        members: Sequence[str] | None = None,
    ) -> SplitProfile:
        history = [
            SplitVersion(from_month=m, shares=Builders.shares(*pairs)) for m, pairs in versions
        ]
        if members is None:
            members = list(dict.fromkeys(u for _, pairs in versions for u, _ in pairs))
        return SplitProfile(
            id=sid,
            name=sid,
            members=list(members),
            mode=mode,
            history=history,  # type: ignore[arg-type]
        )

    @staticmethod
    def ref(sid: str) -> SplitRef:
        return SplitRef(split_id=sid)

    # ------------------------------------------------------------ cards and accounts

    @staticmethod
    def card(
        cid: str = "card_x",
        closing: int = 3,
        due: int = 10,
        *,
        billing: Sequence[tuple[str, int, int]] | None = None,
        owners: Allocation | None = None,
        responsible: str | None = EU,
        parent: str | None = None,
        account: str | None = None,
    ) -> Card:
        if parent is not None:
            history: list[BillingEntry] = []
        elif billing is not None:
            history = [BillingEntry(from_month=m, closing_day=c, due_day=d) for m, c, d in billing]
        else:
            history = [BillingEntry(from_month="2020-01", closing_day=closing, due_day=due)]
        if owners is None and parent is None and account is None:
            owners = Builders.shares((EU, 100))
        return Card(
            id=cid,
            name=cid,
            parent_card_id=parent,
            account_id=account,
            owners=owners,
            responsible_user_id=responsible,
            billing_history=history,
        )

    @staticmethod
    def account(
        aid: str = "acc_x",
        *,
        owners: Allocation | None = None,
        responsible: str = EU,
        type: str = "checking",
        confirm_after: int | None = None,
    ) -> Account:
        return Account(
            id=aid,
            name=aid,
            type=type,  # type: ignore[arg-type]
            owners=owners if owners is not None else Builders.shares((EU, 100)),
            responsible_user_id=responsible,
            confirm_manual_after_days=confirm_after,
        )

    # ------------------------------------------------------------ transactions

    @staticmethod
    def tx(
        tid: str,
        amount: str | int,
        *,
        month: str,
        day: date,
        card: str | None = None,
        account: str | None = None,
        method: PaymentMethod | None = None,
        kind: Kind = Kind.EXPENSE,
        manual: bool = False,
        sha: str | None = None,
        provisional: bool | None = None,
        category: str | None = None,
        allocations: Allocation | None = None,
        description: str | None = None,
        review_status: str | None = None,
    ) -> Transaction:
        if method is None:
            method = PaymentMethod.CREDIT if card else PaymentMethod.DEBIT
        if provisional is None:
            provisional = manual and method is not PaymentMethod.CASH
        source = Source(type="manual") if manual else Source(type="import", sha256=sha or "sha")
        data: dict[str, Any] = {
            "id": tid,
            "kind": kind,
            "source": source,
            "provisional": provisional,
            "payment_method": method,
            "card_id": card,
            "account_id": account,
            "purchase_date": day,
            "invoice_month": month,
            "description": description or tid.upper(),
            "amount": D(amount),
            "category_id": category,
            "allocations": allocations,
        }
        if review_status is not None:
            data["review"] = {"status": review_status}
        return Transaction.model_validate(data)

    # ------------------------------------------------------------ plans, subs, recurring

    @staticmethod
    def plan(
        pid: str = "plan_1",
        *,
        n: int = 10,
        total: str | int = 1500,
        first: str = "2026-08",
        card: str = "card_x",
        imported_amount: str | int | None = None,
        allocations: Allocation | None = None,
        category: str | None = None,
        description: str = "LOJA X",
    ) -> InstallmentPlan:
        data: dict[str, Any] = {
            "id": pid,
            "card_id": card,
            "description": description,
            "total_installments": n,
            "first_invoice_month": first,
            "total_amount": D(total),
            "allocations": allocations,
            "category_id": category,
        }
        if imported_amount is not None:
            data["origin"] = {"type": "import", "fingerprint": "fp_plan"}
            data["installment_amount"] = D(imported_amount)
        return InstallmentPlan.model_validate(data)

    @staticmethod
    def subscription(
        sid: str = "sub_1",
        amount: str | int = 50,
        *,
        start: str = "2026-01",
        end: str | None = None,
        period: str = "monthly",
        month_of_year: int | None = None,
        card: str | None = "card_x",
        account: str | None = None,
        method: PaymentMethod = PaymentMethod.CREDIT,
        allocations: Allocation | None = None,
    ) -> Subscription:
        return Subscription.model_validate(
            {
                "id": sid,
                "description": sid.upper(),
                "amount": D(amount),
                "period": period,
                "month_of_year": month_of_year,
                "payment_method": method,
                "card_id": card,
                "account_id": account,
                "start_month": start,
                "end_month": end,
                "allocations": allocations,
            }
        )

    @staticmethod
    def recurring(
        rid: str = "rec_racao",
        *,
        last: date = date(2026, 9, 20),
        every: int = 45,
        unit: str = "days",
        amount: str | int = 250,
        card: str | None = "card_x",
        account: str | None = None,
        method: PaymentMethod = PaymentMethod.CREDIT,
        active: bool = True,
        skipped: Sequence[date] = (),
    ) -> RecurringPurchase:
        return RecurringPurchase.model_validate(
            {
                "id": rid,
                "description": "RACAO GATOS",
                "match_description": "PETZ|COBASI",
                "estimated_amount": D(amount),
                "every": {"value": every, "unit": unit},
                "last_date": last,
                "payment_method": method,
                "card_id": card,
                "account_id": account,
                "active": active,
                "skipped_dates": list(skipped),
            }
        )

    # ------------------------------------------------------------ rules, settlements

    @staticmethod
    def rule(
        rid: str,
        *,
        priority: int = 100,
        enabled: bool = True,
        when: dict[str, Any] | None = None,
        category: str | None = None,
        allocations: Allocation | None = None,
    ) -> Rule:
        return Rule.model_validate(
            {
                "id": rid,
                "priority": priority,
                "enabled": enabled,
                "when": when or {},
                "then": {"category_id": category, "allocations": allocations},
            }
        )

    @staticmethod
    def settlement(
        frm: str, to: str, amount: str | int, month: str, sid: str = "set_1"
    ) -> Settlement:
        return Settlement(
            id=sid,
            from_user_id=frm,
            to_user_id=to,
            amount=D(amount),
            date=date(int(month[:4]), int(month[5:]), 15),
            month=month,
        )

    # ------------------------------------------------------------ investments

    @staticmethod
    def investment(
        iid: str = "inv_reserva",
        *,
        owners: Allocation | None = None,
        snapshots: Sequence[tuple[date, str | int]] = (),
        movements: Sequence[tuple[date, str, str | int]] = (),
        goal: str | None = None,
        type: str = "emergency_reserve",
        closed_at: date | None = None,
    ) -> Investment:
        return Investment(
            id=iid,
            name=iid,
            type=type,  # type: ignore[arg-type]
            owners=owners if owners is not None else Builders.shares((EU, 100)),
            goal_id=goal,
            snapshots=[Snapshot(date=d, balance=D(b)) for d, b in snapshots],
            movements=[Movement(date=d, type=t, amount=D(a)) for d, t, a in movements],  # type: ignore[arg-type]
            closed_at=closed_at,
        )

    # ------------------------------------------------------------ ledger

    @staticmethod
    def invoice(
        sha: str,
        month: str,
        *,
        card: str = "card_x",
        status: str = "confirmed",
        open_invoice: bool = False,
        as_of: date | None = None,
        closing_date: date | None = None,
    ) -> DocumentInfo:
        return DocumentInfo(
            sha256=sha,
            kind="fatura",
            status=status,
            card_id=card,
            invoice_month=month,
            open_invoice=open_invoice,
            as_of=as_of,
            closing_date=closing_date,
        )

    @staticmethod
    def statement(
        sha: str, account: str, start: date, end: date, *, status: str = "confirmed"
    ) -> DocumentInfo:
        return DocumentInfo(
            sha256=sha,
            kind="extrato",
            status=status,
            account_id=account,
            period_from=start,
            period_to=end,
        )

    @staticmethod
    def state(
        *,
        users: Sequence[User] = (),
        splits: Sequence[SplitProfile] = (),
        cards: Sequence[Card] = (),
        accounts: Sequence[Account] = (),
        transactions: Sequence[Transaction] = (),
        staging: Sequence[Transaction] = (),
        plans: Sequence[InstallmentPlan] = (),
        subscriptions: Sequence[Subscription] = (),
        recurring: Sequence[RecurringPurchase] = (),
        documents: Sequence[DocumentInfo] = (),
    ) -> LedgerState:
        if not users:
            users = [Builders.user(EU), Builders.user(ANA), Builders.user(PAIS)]
        return LedgerState(
            users={u.id: u for u in users},
            splits={s.id: s for s in splits},
            cards={c.id: c for c in cards},
            accounts={a.id: a for a in accounts},
            transactions=list(transactions),
            staging=list(staging),
            plans=list(plans),
            subscriptions=list(subscriptions),
            recurring=list(recurring),
            documents=list(documents),
        )

    @staticmethod
    def ledger(today: date, include_pending: bool = False, **state: Any) -> Ledger:
        return Ledger(Builders.state(**state), today, include_pending=include_pending)
