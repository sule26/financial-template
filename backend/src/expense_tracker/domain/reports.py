"""Aggregations over the ledger: summary, projection, balances, committed income (docs/07, 08)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

from expense_tracker.domain.allocation import income_for
from expense_tracker.domain.ledger import Ledger, LedgerItem, MonthView
from expense_tracker.domain.models import PaymentMethod, SavingsGoal, Settlement, User
from expense_tracker.domain.money import CENT, HUNDRED, ZERO
from expense_tracker.domain.months import due_date_of_month

UNCATEGORIZED = "__none__"

METHOD_GROUPS: dict[PaymentMethod, str] = {
    PaymentMethod.CREDIT: "credit",
    PaymentMethod.BENEFIT: "benefit",
    PaymentMethod.DEBIT: "account",
    PaymentMethod.PIX: "account",
    PaymentMethod.TRANSFER: "account",
    PaymentMethod.BOLETO: "account",
    PaymentMethod.CASH: "cash",
}


def amount_for(ledger: Ledger, item: LedgerItem, user_id: str | None) -> Decimal:
    if user_id is None:
        return item.amount
    return ledger.parts_of(item).get(user_id, ZERO)


def is_card_item(ledger: Ledger, item: LedgerItem) -> bool:
    """R14.2: bought on a credit card (main or additional) or on a benefit card (VR/VA)."""
    if item.card_id:
        return True
    account = ledger.s.accounts.get(item.account_id or "")
    return account is not None and account.type == "benefit"


def cards_view(ledger: Ledger, view: MonthView) -> MonthView:
    """R14.2: the month restricted to cards; checking and cash accounts are left out."""
    benefit = {a.id for a in ledger.s.accounts.values() if a.type == "benefit"}
    return MonthView(
        month=view.month,
        items=[i for i in view.items if is_card_item(ledger, i)],
        states={k: v for k, v in view.states.items() if k in ledger.s.cards or k in benefit},
        warnings=list(view.warnings),
    )


@dataclass
class MonthSummary:
    month: str
    total: Decimal
    by_category: dict[str, Decimal]
    by_card: dict[str, Decimal]
    by_method: dict[str, Decimal]
    states: dict[str, str]
    income: Decimal | None = None
    benefit_income: Decimal | None = None


def summarize(
    ledger: Ledger,
    view: MonthView,
    user: User | None = None,
    method_group: str | None = None,
) -> MonthSummary:
    """Totals of one month view; with ``user`` each item counts only that user's part."""
    uid = user.id if user else None
    by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_card: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_method: dict[str, Decimal] = defaultdict(lambda: ZERO)
    total = ZERO
    for item in view.items:
        if not item.counts_as_spending:
            continue
        group = METHOD_GROUPS[item.payment_method]
        if method_group and group != method_group:
            continue
        value = amount_for(ledger, item, uid)
        if value == ZERO:
            continue
        total += value
        by_cat[item.category_id or UNCATEGORIZED] += value
        owner = ledger.main_card(item.card_id) if item.card_id else (item.account_id or "")
        by_card[owner] += value
        by_method[group] += value
    return MonthSummary(
        month=view.month,
        total=total,
        by_category=dict(by_cat),
        by_card=dict(by_card),
        by_method=dict(by_method),
        states=dict(view.states),
        income=_income(ledger, view.month, user, benefit=False),
        benefit_income=_income(ledger, view.month, user, benefit=True),
    )


def _income(ledger: Ledger, month: str, user: User | None, *, benefit: bool) -> Decimal | None:
    """Income of the person; with no person, of the household (sum of every user, R14.6)."""
    benefits = ledger.s.benefits
    if user is not None:
        return income_for(user, month, benefit=benefit, benefits=benefits)
    values = [
        income_for(u, month, benefit=benefit, benefits=benefits) for u in ledger.s.users.values()
    ]
    present = [v for v in values if v is not None]
    return sum(present, ZERO) if present else None


@dataclass
class Commitment:
    month: str
    spent: Decimal
    income: Decimal | None
    ratio: Decimal | None  # percentage
    benefit_spent: Decimal
    benefit_income: Decimal | None
    benefit_ratio: Decimal | None
    band: str | None


def _ratio(spent: Decimal, income: Decimal | None) -> Decimal | None:
    if income is None or income == ZERO:
        return None
    return (spent * HUNDRED / income).quantize(CENT, rounding=ROUND_HALF_EVEN)


def band(
    ratio: Decimal | None, warn: Decimal = Decimal(50), alert: Decimal = Decimal(80)
) -> str | None:
    if ratio is None:
        return None
    if ratio < warn:
        return "green"
    if ratio <= alert:
        return "yellow"
    return "red"


def committed_income(ledger: Ledger, views: Iterable[MonthView], user: User) -> list[Commitment]:
    """R1.9: user's part of spending / income in force; benefit compared separately."""
    out: list[Commitment] = []
    for view in views:
        cash = ZERO
        benefit = ZERO
        for item in view.items:
            if not item.counts_as_spending:
                continue
            part = ledger.parts_of(item).get(user.id, ZERO)
            if item.payment_method is PaymentMethod.BENEFIT:
                benefit += part
            else:
                cash += part
        inc = income_for(user, view.month, benefits=ledger.s.benefits)
        binc = income_for(user, view.month, benefit=True, benefits=ledger.s.benefits)
        ratio = _ratio(cash, inc)
        out.append(
            Commitment(
                view.month, cash, inc, ratio, benefit, binc, _ratio(benefit, binc), band(ratio)
            )
        )
    return out


# ------------------------------------------------------------------- balances


@dataclass
class BalanceLine:
    month: str
    ref_id: str
    description: str
    creditor: str
    debtor: str
    amount: Decimal
    card_id: str | None = None  # main card (the one that owns the invoice)
    account_id: str | None = None  # set only for items paid from an account
    due_date: date | None = None  # due date of the card invoice; None for accounts


def creditor_for(debtor: str, responsible: str, users: Mapping[str, User]) -> str:
    """R13.11: the debtor's "repassar para" user when set, else the responsible."""
    user = users.get(debtor)
    collector = user.collector_user_id if user is not None else None
    return collector if collector and collector != debtor else responsible


def invoice_due_date(ledger: Ledger, main_card: str, month: str) -> date | None:
    """Due date of a card invoice: the active document's, else the planned one (docs/07)."""
    doc = ledger.document_for(main_card, month)
    if doc is not None and doc.due_date is not None:
        return doc.due_date
    card = ledger.s.cards.get(main_card)
    if card is None:
        return None
    return due_date_of_month(card.billing_history, month)


@dataclass
class Balances:
    """``net[(a, b)] > 0`` means b owes a."""

    lines: list[BalanceLine] = field(default_factory=list)
    settlements: list[Settlement] = field(default_factory=list)
    incomplete_months: set[str] = field(default_factory=set)

    def net(self, a: str, b: str, month: str | None = None) -> Decimal:
        total = ZERO
        for line in self.lines:
            if month and line.month != month:
                continue
            if line.creditor == a and line.debtor == b:
                total += line.amount
            elif line.creditor == b and line.debtor == a:
                total -= line.amount
        for s in self.settlements:
            if month and s.month != month:
                continue
            if s.from_user_id == b and s.to_user_id == a:
                total -= s.amount
            elif s.from_user_id == a and s.to_user_id == b:
                total += s.amount
        return total

    def counterparties(self, user_id: str) -> list[str]:
        others: set[str] = set()
        for line in self.lines:
            if user_id in (line.creditor, line.debtor):
                others.add(line.debtor if line.creditor == user_id else line.creditor)
        for s in self.settlements:
            if user_id in (s.from_user_id, s.to_user_id):
                others.add(s.to_user_id if s.from_user_id == user_id else s.from_user_id)
        others.discard(user_id)
        return sorted(others)


def balances(
    ledger: Ledger, views: Iterable[MonthView], settlements: Sequence[Settlement]
) -> Balances:
    """Debts from spending items (docs/08 "Saldos").

    Each user owes their part to each payer of the card/account in proportion (R14.1; a single
    payer is the responsible, R6.8), except the share they pay themselves. The debt goes to the
    debtor's collector ("repassar para", R13.11) when set; a collector who is not that payer
    owes the same amount on to the payer (R13.14, same card/account, due date and month). Pure
    forecasts (plans, subscriptions, recurring) are not debts yet; transactions (imported or
    manual) are.
    """
    result = Balances(settlements=list(settlements))
    users = ledger.s.users
    due_cache: dict[tuple[str, str], date | None] = {}
    for view in views:
        if any(state == "missing" for state in view.states.values()):
            result.incomplete_months.add(view.month)
        for item in view.items:
            if not item.counts_as_spending or item.is_forecast:
                continue
            card_id = ledger.main_card(item.card_id) if item.card_id else None
            account_id = None if card_id else item.account_id
            due: date | None = None
            if card_id is not None:
                key = (card_id, view.month)
                if key not in due_cache:
                    due_cache[key] = invoice_due_date(ledger, card_id, view.month)
                due = due_cache[key]
            for uid, value in ledger.parts_of(item).items():
                if value == ZERO:
                    continue
                # R14.1: the part is owed to each payer in proportion; one payer = R6.8.
                for payer, owed in ledger.owed_to_payers(item, value).items():
                    if uid == payer or owed == ZERO:
                        continue
                    # creditor_for never returns the debtor: own parts are skipped above.
                    creditor = creditor_for(uid, payer, users)
                    pairs = [(creditor, uid)]
                    if creditor != payer:
                        # R13.14: the collector passes the amount on to the payer.
                        pairs.append((payer, creditor))
                    for cred, debtor in pairs:
                        result.lines.append(
                            BalanceLine(
                                view.month,
                                item.ref_id,
                                item.description,
                                cred,
                                debtor,
                                owed,
                                card_id,
                                account_id,
                                due,
                            )
                        )
    return result


ReceivableStatus = Literal["open", "partial", "received"]


@dataclass(frozen=True)
class Receivable:
    """One "a receber/a pagar" entry per counterparty, main card or account and invoice month."""

    counterparty_user_id: str
    direction: Literal["receive", "pay"]
    card_id: str | None
    account_id: str | None
    invoice_month: str
    due_date: date | None
    amount: Decimal  # always positive
    overdue: bool  # due date passed and something is still to be paid
    settled_month_total: Decimal  # settlements of the month, + received / − paid by the user
    settled: Decimal = ZERO  # R13.16: linked settlements in the item's direction
    remaining: Decimal = ZERO  # max(amount − settled, 0)
    status: ReceivableStatus = "open"


def _status(settled: Decimal, remaining: Decimal) -> ReceivableStatus:
    if remaining == ZERO:
        return "received"
    return "partial" if settled > ZERO else "open"


def linked_settled(
    settlements: Iterable[Settlement],
    payer: str,
    payee: str,
    card_id: str | None,
    account_id: str | None,
    invoice_month: str,
) -> Decimal:
    """R13.16: Σ settlements payer → payee linked to this card/account and invoice month."""
    total = ZERO
    for s in settlements:
        if (
            s.linked
            and s.from_user_id == payer
            and s.to_user_id == payee
            and s.card_id == card_id
            and s.account_id == account_id
            and s.invoice_month == invoice_month
        ):
            total += s.amount
    return total


def receivables(bal: Balances, user_id: str, today: date) -> list[Receivable]:
    """R13.11/R13.16: group the user's debts/credits by (counterparty, card or account, month).

    Within a group, credits and debts are netted. Settlements linked to the group (same pair and
    direction, card/account and invoice month) reduce ``remaining``; unlinked settlements are not
    distributed over the groups (the net balance stays in ``Balances.net``), only reported per
    month and pair in ``settled_month_total``.
    Sorted by due date (accounts, without due date, last), then month and counterparty.
    """
    groups: dict[tuple[str, str | None, str | None, str], Decimal] = defaultdict(lambda: ZERO)
    dues: dict[tuple[str, str | None, str | None, str], date | None] = {}
    for line in bal.lines:
        if user_id == line.creditor:
            other, sign = line.debtor, Decimal(1)
        elif user_id == line.debtor:
            other, sign = line.creditor, Decimal(-1)
        else:
            continue
        key = (other, line.card_id, line.account_id, line.month)
        groups[key] += sign * line.amount
        dues[key] = line.due_date
    out: list[Receivable] = []
    for key, net in groups.items():
        if net == ZERO:
            continue
        other, card_id, account_id, month = key
        settled = ZERO
        for s in bal.settlements:
            if s.month != month:
                continue
            if s.from_user_id == other and s.to_user_id == user_id:
                settled += s.amount
            elif s.from_user_id == user_id and s.to_user_id == other:
                settled -= s.amount
        due = dues[key]
        direction: Literal["receive", "pay"] = "receive" if net > ZERO else "pay"
        payer, payee = (other, user_id) if direction == "receive" else (user_id, other)
        paid = linked_settled(bal.settlements, payer, payee, card_id, account_id, month)
        amount = abs(net)
        remaining = max(amount - paid, ZERO)
        out.append(
            Receivable(
                counterparty_user_id=other,
                direction=direction,
                card_id=card_id,
                account_id=account_id,
                invoice_month=month,
                due_date=due,
                amount=amount,
                overdue=remaining > ZERO and due is not None and due < today,
                settled_month_total=settled,
                settled=paid,
                remaining=remaining,
                status=_status(paid, remaining),
            )
        )
    out.sort(
        key=lambda r: (
            r.due_date is None,
            r.due_date or date.min,
            r.invoice_month,
            r.counterparty_user_id,
            r.card_id or "",
            r.account_id or "",
        )
    )
    return out


def settlement_impact(
    before: Balances, after: Balances, months: Iterable[str]
) -> list[tuple[str, str, str, Decimal, Decimal]]:
    """R6.13: per settled month and pair, (month, a, b, old_net, new_net) that changed."""
    changed: list[tuple[str, str, str, Decimal, Decimal]] = []
    settled = {(s.month, *sorted((s.from_user_id, s.to_user_id))) for s in before.settlements}
    wanted = set(months)
    for month, a, b in sorted(settled):
        if month not in wanted:
            continue
        old, new = before.net(a, b, month), after.net(a, b, month)
        if old != new:
            changed.append((month, a, b, old, new))
    return changed


def goals_progress(
    goals: Sequence[SavingsGoal], contributions_by_goal: Mapping[str, Decimal]
) -> dict[str, tuple[Decimal, Decimal]]:
    """goal id -> (target, achieved) for one month (docs/07 "Metas de poupança")."""
    return {g.id: (g.monthly_amount, contributions_by_goal.get(g.id, ZERO)) for g in goals}
