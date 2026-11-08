"""Ledger: real x projected per (card, month) and (account, month) (docs/07 "Real x projetado").

This is the single function every panel uses (summary, projection, balances, committed income),
so there is exactly one source per (card, month) and nothing is counted twice.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from typing import Literal

from expense_tracker.domain.allocation import (
    AllocationError,
    Ownership,
    ResolvedSplit,
    main_card_id,
    parts,
    resolve_account,
    resolve_allocation,
    resolve_card,
)
from expense_tracker.domain.installments import schedule
from expense_tracker.domain.models import (
    SPENDING_KINDS,
    Account,
    Allocation,
    Benefit,
    Card,
    InstallmentPlan,
    Kind,
    PaymentMethod,
    RecurringPurchase,
    Share,
    SplitProfile,
    Subscription,
    Transaction,
    User,
)
from expense_tracker.domain.money import HUNDRED, ZERO
from expense_tracker.domain.months import (
    add_months,
    current_invoice_month,
    due_date_of_month,
    invoice_month,
    month_of,
)
from expense_tracker.domain.recurrence import recurring_charges, subscription_charges

ACTIVE_STATUSES = frozenset({"pending_review", "partially_confirmed", "confirmed"})


@dataclass(frozen=True)
class DocumentInfo:
    """What the ledger needs to know about an imported file (manifest entry)."""

    sha256: str
    kind: Literal["fatura", "extrato"]
    status: str
    card_id: str | None = None  # main card id
    account_id: str | None = None
    invoice_month: str | None = None
    open_invoice: bool = False
    as_of: date | None = None
    period_from: date | None = None
    period_to: date | None = None
    amount_due: Decimal | None = None
    total: Decimal | None = None
    due_date: date | None = None
    closing_date: date | None = None
    paid_by_fingerprints: tuple[str, ...] = ()
    supersedes_candidate: str | None = None

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES


@dataclass
class LedgerState:
    """Everything the ledger reads. Built by the service layer from storage."""

    users: Mapping[str, User]
    splits: Mapping[str, SplitProfile]
    cards: Mapping[str, Card]
    accounts: Mapping[str, Account]
    transactions: Sequence[Transaction]
    staging: Sequence[Transaction] = ()
    plans: Sequence[InstallmentPlan] = ()
    subscriptions: Sequence[Subscription] = ()
    recurring: Sequence[RecurringPurchase] = ()
    documents: Sequence[DocumentInfo] = ()
    benefits: Sequence[Benefit] = ()


Origin = Literal["transaction", "staging", "plan", "anticipation", "subscription", "recurring"]


@dataclass(frozen=True)
class LedgerItem:
    month: str
    description: str
    amount: Decimal
    kind: Kind
    payment_method: PaymentMethod
    origin: Origin
    card_id: str | None
    account_id: str | None
    category_id: str | None
    allocations: Allocation | None
    responsible_user_id: str
    owners: Allocation
    ref_id: str
    purchase_date: date | None = None
    provisional: bool = False
    responsibles: Allocation | None = None  # R14.1
    installment: tuple[int, int] | None = None  # R14.19: (n, of) of a planned installment

    @property
    def is_forecast(self) -> bool:
        return self.origin in ("plan", "anticipation", "subscription", "recurring")

    @property
    def counts_as_spending(self) -> bool:
        return self.kind in SPENDING_KINDS


MonthState = Literal["real", "open", "projected", "missing"]


@dataclass
class MonthView:
    month: str
    items: list[LedgerItem] = field(default_factory=list)
    states: dict[str, MonthState] = field(default_factory=dict)  # card main id / account id
    warnings: list[str] = field(default_factory=list)


class Ledger:
    """Computes month views from a ``LedgerState``."""

    def __init__(self, state: LedgerState, today: date, include_pending: bool = False) -> None:
        self.s = state
        self.today = today
        self.include_pending = include_pending
        self._ownership: dict[str, Ownership] = {}
        self._docs_by_card_month: dict[tuple[str, str], DocumentInfo] = {}
        self._statements: dict[str, list[DocumentInfo]] = defaultdict(list)
        for doc in state.documents:
            if not doc.active:
                continue
            if doc.kind == "fatura" and doc.card_id and doc.invoice_month:
                # A pending candidate replacement never hides the active document (docs/05).
                if doc.supersedes_candidate:
                    continue
                self._docs_by_card_month[(doc.card_id, doc.invoice_month)] = doc
            elif doc.kind == "extrato" and doc.account_id:
                self._statements[doc.account_id].append(doc)
        self._by_sha: dict[str, list[Transaction]] = defaultdict(list)
        for tx in state.transactions:
            if tx.source.sha256:
                self._by_sha[tx.source.sha256].append(tx)
        # R14.26: a subscription month already paid by a linked transaction is not forecast again
        self.subscription_paid: set[tuple[str, str]] = {
            (tx.links.subscription_id, tx.links.subscription_month or tx.invoice_month)
            for tx in state.transactions
            if tx.links.subscription_id
        }
        # R14.26: household bill months already paid by a linked entry
        self.recurring_paid: set[tuple[str, str]] = {
            (tx.links.recurring_purchase_id, tx.links.recurring_month)
            for tx in state.transactions
            if tx.links.recurring_purchase_id and tx.links.recurring_month
        }
        self._staging_by_sha: dict[str, list[Transaction]] = defaultdict(list)
        for tx in state.staging:
            if tx.source.sha256 and (tx.review is None or tx.review.status != "overlap"):
                self._staging_by_sha[tx.source.sha256].append(tx)

    # ------------------------------------------------------------ ownership helpers

    def card_ownership(self, card_id: str) -> Ownership:
        key = f"card:{card_id}"
        if key not in self._ownership:
            card = self.s.cards.get(card_id)
            if card is None:
                raise AllocationError(f"unknown card {card_id}")
            self._ownership[key] = resolve_card(card, self.s.cards, self.s.accounts)
        return self._ownership[key]

    def account_ownership(self, account_id: str) -> Ownership:
        key = f"acc:{account_id}"
        if key not in self._ownership:
            acc = self.s.accounts.get(account_id)
            if acc is None:
                raise AllocationError(f"unknown account {account_id}")
            self._ownership[key] = resolve_account(acc)
        return self._ownership[key]

    def main_card(self, card_id: str) -> str:
        card = self.s.cards.get(card_id)
        return main_card_id(card) if card else card_id

    def billing(self, card_id: str) -> list[object]:
        card = self.s.cards[self.main_card(card_id)]
        return list(card.billing_history)

    def card_h(self, card_id: str) -> str:
        """``H(card)``: current open invoice month of the card."""
        main = self.s.cards[self.main_card(card_id)]
        return current_invoice_month(main.billing_history, self.today)

    def month_for_card_date(self, card_id: str, d: date) -> str:
        main = self.s.cards[self.main_card(card_id)]
        actual = {
            month_of(doc.closing_date): doc.closing_date
            for (cid, _), doc in self._docs_by_card_month.items()
            if cid == main.id and doc.closing_date is not None
        }
        return invoice_month(main.billing_history, d, actual)

    def document_for(self, card_id: str, month: str) -> DocumentInfo | None:
        return self._docs_by_card_month.get((self.main_card(card_id), month))

    # ------------------------------------------------------------ item builders

    def _tx_item(self, tx: Transaction, origin: Origin) -> LedgerItem | None:
        try:
            own = (
                self.card_ownership(tx.card_id)
                if tx.card_id
                else self.account_ownership(tx.account_id or "")
            )
        except AllocationError:
            return None
        return LedgerItem(
            month=tx.invoice_month,
            description=tx.description,
            amount=tx.amount,
            kind=tx.kind,
            payment_method=tx.payment_method,
            origin=origin,
            card_id=tx.card_id,
            account_id=tx.account_id,
            category_id=tx.category_id,
            allocations=tx.allocations,
            responsible_user_id=own.responsible_user_id,
            owners=own.owners,
            ref_id=tx.id,
            purchase_date=tx.purchase_date,
            provisional=tx.provisional,
            responsibles=own.responsibles,
        )

    def _forecast(
        self,
        *,
        month: str,
        description: str,
        amount: Decimal,
        origin: Origin,
        ref_id: str,
        card_id: str | None,
        account_id: str | None,
        method: PaymentMethod,
        category_id: str | None,
        allocations: Allocation | None,
        purchase_date: date | None = None,
    ) -> LedgerItem | None:
        try:
            own = (
                self.card_ownership(card_id)
                if card_id
                else self.account_ownership(account_id or "")
            )
        except AllocationError:
            return None
        return LedgerItem(
            month=month,
            description=description,
            amount=amount,
            kind=Kind.EXPENSE,
            payment_method=method,
            origin=origin,
            card_id=card_id,
            account_id=account_id,
            category_id=category_id,
            allocations=allocations,
            responsible_user_id=own.responsible_user_id,
            owners=own.owners,
            ref_id=ref_id,
            purchase_date=purchase_date,
            responsibles=own.responsibles,
        )

    # ------------------------------------------------------------ cards

    def _card_forecasts(self, main_id: str, month: str, after: date | None) -> list[LedgerItem]:
        items: list[LedgerItem] = []
        if after is None:
            for plan in self.s.plans:
                if self.main_card(plan.card_id) != main_id:
                    continue
                for charge in schedule(plan):
                    if charge.month != month:
                        continue
                    desc = plan.description
                    if charge.kind == "anticipation":
                        desc = f"Antecipação {plan.description} ({charge.range_from}–"
                        desc += f"{charge.range_to}/{plan.total_installments})"
                    item = self._forecast(
                        month=month,
                        description=desc,
                        amount=charge.amount,
                        origin="plan" if charge.kind == "installment" else "anticipation",
                        ref_id=plan.id,
                        card_id=plan.card_id,
                        account_id=None,
                        method=PaymentMethod.CREDIT,
                        category_id=plan.category_id,
                        allocations=plan.allocations,
                    )
                    if item:
                        if charge.kind == "installment" and charge.n is not None:
                            item = replace(item, installment=(charge.n, plan.total_installments))
                        items.append(item)
            for sub in self.s.subscriptions:
                if not sub.card_id or self.main_card(sub.card_id) != main_id:
                    continue
                for ch in subscription_charges(sub, [month]):
                    if (sub.id, month) in self.subscription_paid:
                        continue
                    item = self._forecast(
                        month=month,
                        description=sub.description,
                        amount=ch.amount,
                        origin="subscription",
                        ref_id=sub.id,
                        card_id=sub.card_id,
                        account_id=None,
                        method=PaymentMethod.CREDIT,
                        category_id=sub.category_id,
                        allocations=sub.allocations_in(month),
                    )
                    if item:
                        items.append(item)
        for rec in self.s.recurring:
            if not rec.card_id or self.main_card(rec.card_id) != main_id:
                continue
            card_id = rec.card_id
            for ch in recurring_charges(rec, [month], partial(self.month_for_card_date, card_id)):
                if after is not None and ch.date is not None and ch.date <= after:
                    continue
                if ch.date is not None and (rec.id, month_of(ch.date)) in self.recurring_paid:
                    continue
                item = self._forecast(
                    month=month,
                    description=rec.description,
                    amount=ch.amount,
                    origin="recurring",
                    ref_id=rec.id,
                    card_id=card_id,
                    account_id=None,
                    method=rec.payment_method,
                    category_id=rec.category_id,
                    allocations=rec.allocations_in(month_of(ch.date) if ch.date else month),
                    purchase_date=ch.date,
                )
                if item:
                    items.append(item)
        return items

    def card_month(self, main_id: str, month: str) -> tuple[MonthState, list[LedgerItem]]:
        doc = self.document_for(main_id, month)
        manual = [
            tx
            for tx in self.s.transactions
            if tx.source.type == "manual"
            and tx.card_id
            and self.main_card(tx.card_id) == main_id
            and tx.invoice_month == month
        ]
        definitive = [self._tx_item(t, "transaction") for t in manual if not t.provisional]
        provisional = [t for t in manual if t.provisional]
        use_real = doc is not None and (self.include_pending or doc.status != "pending_review")
        items: list[LedgerItem | None] = list(definitive)
        if use_real and doc is not None:
            items += [self._tx_item(t, "transaction") for t in self._by_sha.get(doc.sha256, [])]
            if self.include_pending:
                items += [
                    self._tx_item(t, "staging") for t in self._staging_by_sha.get(doc.sha256, [])
                ]
            if doc.open_invoice:
                after = doc.as_of or self.today
                items += [
                    self._tx_item(t, "transaction") for t in provisional if t.purchase_date > after
                ]
                items += self._card_forecasts(main_id, month, after)
                state: MonthState = "open"
            else:
                state = "real"
        else:
            items += [self._tx_item(t, "transaction") for t in provisional]
            items += self._card_forecasts(main_id, month, None)
            main_card = self.s.cards[main_id]
            # a billing change may leave a month with no invoice at all: empty, not "faltando"
            missing = (
                doc is None
                and month < self.card_h(main_id)
                and due_date_of_month(main_card.billing_history, month) is not None
            )
            state = "missing" if missing else "projected"
        return state, [i for i in items if i is not None]

    # ------------------------------------------------------------ accounts

    def _covered(self, account_id: str, d: date) -> bool:
        for doc in self._statements.get(account_id, []):
            if not self.include_pending and doc.status == "pending_review":
                continue
            if doc.period_from and doc.period_to and doc.period_from <= d <= doc.period_to:
                return True
        return False

    def _month_fully_covered(self, account_id: str, month: str) -> bool:
        y, m = int(month[:4]), int(month[5:])
        d = date(y, m, 1)
        while d.month == m:
            if not self._covered(account_id, d):
                return False
            d += timedelta(days=1)
        return True

    def _month_touched(self, account_id: str, month: str) -> bool:
        y, m = int(month[:4]), int(month[5:])
        d = date(y, m, 1)
        while d.month == m:
            if self._covered(account_id, d):
                return True
            d += timedelta(days=1)
        return False

    def account_month(self, account_id: str, month: str) -> tuple[MonthState, list[LedgerItem]]:
        acc = self.s.accounts[account_id]
        items: list[LedgerItem | None] = []
        for tx in self.s.transactions:
            if tx.account_id != account_id or tx.card_id or tx.invoice_month != month:
                continue
            # Provisional manual entries count only on days not covered by a statement; an old
            # one on an account without statements becomes definitive (docs/16).
            if (
                tx.source.type == "import"
                or not tx.provisional
                or acc.type == "cash"
                or not self._covered(account_id, tx.purchase_date)
            ):
                items.append(self._tx_item(tx, "transaction"))
        if self.include_pending:
            for tx in self.s.staging:
                if (
                    tx.account_id == account_id
                    and not tx.card_id
                    and tx.invoice_month == month
                    and (tx.review is None or tx.review.status != "overlap")
                ):
                    items.append(self._tx_item(tx, "staging"))
        fully = self._month_fully_covered(account_id, month)
        touched = self._month_touched(account_id, month)
        if not touched:
            # Subscriptions have no date: forecast only while no statement covers the month.
            for sub in self.s.subscriptions:
                if sub.account_id == account_id and not sub.card_id:
                    for ch in subscription_charges(sub, [month]):
                        if (sub.id, month) in self.subscription_paid:
                            continue
                        items.append(
                            self._forecast(
                                month=month,
                                description=sub.description,
                                amount=ch.amount,
                                origin="subscription",
                                ref_id=sub.id,
                                card_id=None,
                                account_id=account_id,
                                method=sub.payment_method,
                                category_id=sub.category_id,
                                allocations=sub.allocations_in(month),
                            )
                        )
        if not fully:
            for rec in self.s.recurring:
                if rec.account_id == account_id and not rec.card_id:
                    for ch in recurring_charges(rec, [month], month_of):
                        if ch.date is not None and self._covered(account_id, ch.date):
                            continue
                        if (
                            ch.date is not None
                            and (rec.id, month_of(ch.date)) in self.recurring_paid
                        ):
                            continue
                        items.append(
                            self._forecast(
                                month=month,
                                description=rec.description,
                                amount=ch.amount,
                                origin="recurring",
                                ref_id=rec.id,
                                card_id=None,
                                account_id=account_id,
                                method=rec.payment_method,
                                category_id=rec.category_id,
                                allocations=rec.allocations_in(
                                    month_of(ch.date) if ch.date else month
                                ),
                                purchase_date=ch.date,
                            )
                        )
        has_docs = bool(self._statements.get(account_id))
        state: MonthState = "real" if fully else ("open" if has_docs else "projected")
        return state, [i for i in items if i is not None]

    # ------------------------------------------------------------ month view

    def month(self, month: str) -> MonthView:
        view = MonthView(month)
        for card in self.s.cards.values():
            if card.parent_card_id:
                continue
            state, items = self.card_month(card.id, month)
            view.states[card.id] = state
            view.items += items
        for acc in self.s.accounts.values():
            state, items = self.account_month(acc.id, month)
            view.states[acc.id] = state
            view.items += items
        return view

    def months(self, months: Iterable[str]) -> list[MonthView]:
        return [self.month(m) for m in months]

    # ------------------------------------------------------------ allocation helpers

    def shares_of(self, item: LedgerItem) -> ResolvedSplit:
        spec = item.allocations if item.allocations is not None else item.owners
        try:
            return resolve_allocation(
                spec, item.month, self.s.splits, self.s.users, self.s.benefits
            )
        except AllocationError:
            return resolve_allocation(
                item.owners, item.month, self.s.splits, self.s.users, self.s.benefits
            )

    def parts_of(self, item: LedgerItem) -> dict[str, Decimal]:
        resolved = self.shares_of(item)
        return parts(item.amount, resolved.shares, item.responsible_user_id)

    def payers_of(self, item: LedgerItem) -> tuple[Share, ...]:
        """R14.1: who pays the bank for this item; unresolvable -> the main responsible."""
        if item.responsibles is not None:
            try:
                return resolve_allocation(
                    item.responsibles, item.month, self.s.splits, self.s.users, self.s.benefits
                ).shares
            except AllocationError:
                pass
        return (Share(user_id=item.responsible_user_id, pct=HUNDRED),)

    def owed_to_payers(self, item: LedgerItem, value: Decimal) -> dict[str, Decimal]:
        """R14.1: a person's part split among the payers by percentage (exact cents; the
        residue goes to the main responsible when paying, else the largest share)."""
        payers = self.payers_of(item)
        return parts(value, payers, item.responsible_user_id)


def projection_months(today: date) -> list[str]:
    """R1.13: always 12 months from the current calendar month."""
    start = month_of(today)
    return [add_months(start, i) for i in range(12)]


def spending_total(items: Iterable[LedgerItem]) -> Decimal:
    return sum((i.amount for i in items if i.counts_as_spending), ZERO)
