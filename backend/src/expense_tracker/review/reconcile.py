"""Reconciliation: suggestions for imported lines (docs/09 "Reconciliação", rows 1–15).

Pure functions over a ``ReconContext`` snapshot. Results are *suggestions*; they only take effect
on confirmation (``review.confirm``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from expense_tracker.domain.installments import installment_month, schedule
from expense_tracker.domain.models import (
    Account,
    Card,
    InstallmentPlan,
    Investment,
    Kind,
    RecurringPurchase,
    Subscription,
    Suggestion,
    Transaction,
    User,
)
from expense_tracker.domain.money import ZERO, money_str
from expense_tracker.domain.months import add_months, month_diff, month_of
from expense_tracker.domain.normalize import normalize_description, similarity
from expense_tracker.domain.recurrence import occurrences, tolerance_days

CENT = Decimal("0.01")


@dataclass
class InvoiceDoc:
    path: str
    sha256: str
    card_id: str
    invoice_month: str
    total: Decimal | None
    amount_due: Decimal | None
    due_date: date | None
    closing_date: date | None


@dataclass
class ReconContext:
    cards: dict[str, Card]
    accounts: dict[str, Account]
    users: dict[str, User]
    plans: list[InstallmentPlan]
    subscriptions: list[Subscription]
    recurring: list[RecurringPurchase]
    investments: list[Investment]
    manuals: list[Transaction]  # provisional manual transactions
    invoices: list[InvoiceDoc]  # active invoice documents
    other_lines: list[Transaction]  # imported lines of other documents (transactions + staging)

    def main(self, card_id: str | None) -> str | None:
        if card_id is None:
            return None
        card = self.cards.get(card_id)
        return (card.parent_card_id or card.id) if card else card_id


@dataclass
class DocResult:
    suggestions: dict[str, list[Suggestion]] = field(default_factory=dict)  # tx id -> list
    statuses: dict[str, str] = field(default_factory=dict)  # tx id -> needs_choice
    warnings: list[str] = field(default_factory=list)


def _close(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    return abs(abs(a) - abs(b)) <= tol


def _pct_close(a: Decimal, b: Decimal, pct: Decimal) -> bool:
    base = max(abs(b), CENT)
    return abs(abs(a) - abs(b)) <= base * pct / 100


def _sugg(
    kind: str,
    target: str | None = None,
    score: float | None = None,
    candidates: Sequence[str] = (),
    **data: Any,
) -> Suggestion:
    return Suggestion(
        type=kind,
        target_id=target,
        score=None if score is None else Decimal(str(round(score, 2))),
        candidates=list(candidates),
        data=data,
    )


def _plan_desc_ok(plan: InstallmentPlan, desc: str, minimum: float = 0.8) -> float:
    return (
        similarity(plan.description, desc) if similarity(plan.description, desc) >= minimum else 0.0
    )


def reconcile_invoice(
    ctx: ReconContext,
    lines: list[Transaction],
    month: str,
    card_main: str,
) -> DocResult:
    """Rows 1–11 for an invoice document."""
    out = DocResult()
    used_plans_n: set[tuple[str, int]] = set()
    used_manuals: set[str] = set()
    card_plans = [p for p in ctx.plans if ctx.main(p.card_id) == card_main]

    def add(tx: Transaction, s: Suggestion) -> None:
        out.suggestions.setdefault(tx.id, []).append(s)

    # row 7b: two or more installments of the same plan in one invoice -> bank anticipation
    bank_anticipated: set[str] = set()
    anchors: dict[str, str] = {}  # tx id -> fingerprint of the line that creates the plan
    discount_plan: tuple[str | None, str | None] | None = None  # (plan id, anchor fingerprint)
    for cluster in _installment_clusters(lines):
        if len(cluster) < 2:
            continue
        if any(_anticipated_plan(card_plans, t, month) for t in cluster):
            continue  # a registered anticipation explains the extra installments (row 5)
        plan = _match_plan(card_plans, cluster[0], month, ignore_n=True)
        regular = [t for t in cluster if t.tag != "anticipation"]
        ns = sorted(t.installment.n for t in cluster if t.installment)
        if plan is not None:
            expected = month_diff(month, plan.first_invoice_month) + 1
        elif regular:
            expected = min(t.installment.n for t in regular if t.installment)
        else:
            expected = ns[0] - 1
        anticipated = [t for t in cluster if t.installment and t.installment.n > expected]
        if not anticipated:
            continue
        from_n = min(t.installment.n for t in anticipated if t.installment)
        anchor = next((t for t in cluster if t.installment and t.installment.n == expected), None)
        anchor_fp = None
        if plan is None:
            anchor = anchor or min(
                anticipated, key=lambda t: t.installment.n if t.installment else 0
            )
            anchor_fp = anchor.fingerprint
        for t in anticipated:
            if anchor is not None and t.id == anchor.id and plan is None:
                continue
            bank_anticipated.add(t.id)
            add(
                t,
                _sugg(
                    "bank_anticipation",
                    plan.id if plan else None,
                    from_n=from_n,
                    plan_fingerprint=anchor_fp,
                ),
            )
        if anchor is not None and plan is None and anchor.installment is not None:
            anchors[anchor.id] = anchor_fp or ""
            if anchor in anticipated:
                bank_anticipated.add(anchor.id)
                add(
                    anchor,
                    _sugg(
                        "create_plan",
                        None,
                        n=anchor.installment.n,
                        of=anchor.installment.of,
                        first_invoice_month=add_months(month, -(expected - 1)),
                        anticipation_from_n=from_n,
                    ),
                )
        if any(t.tag == "anticipation" for t in cluster):
            discount_plan = (plan.id if plan else None, anchor_fp)

    for tx in lines:
        # row 4: refund of an installment plan
        if tx.amount < 0 and tx.kind is Kind.REFUND:
            plan = _best_plan_for_refund(card_plans, tx)
            if plan is not None:
                remaining = sum((c.amount for c in schedule(plan) if c.month > month), ZERO)
                add(
                    tx,
                    _sugg(
                        "refund_plan",
                        plan.id,
                        cancel_suggested=abs(tx.amount) >= remaining and remaining > 0,
                        remaining=money_str(remaining),
                    ),
                )
                continue
        # rows 5/6: anticipation lines and discount
        if tx.tag in ("anticipation", "anticipation_discount") or (
            tx.installment and _anticipated_plan(card_plans, tx, month)
        ):
            plan = _anticipated_plan(card_plans, tx, month)
            if plan is None and tx.tag == "anticipation_discount":
                ants = [
                    p for p in card_plans if p.anticipation and p.anticipation.target_month == month
                ]
                plan = ants[0] if len(ants) == 1 else None
                if plan is None and discount_plan is not None:
                    add(
                        tx,
                        _sugg(
                            "link_anticipation_discount",
                            discount_plan[0],
                            plan_fingerprint=discount_plan[1],
                        ),
                    )
                    continue
            if plan is not None:
                kind = "link_anticipation_discount" if tx.amount < 0 else "link_anticipation"
                add(tx, _sugg(kind, plan.id))
                continue
        if tx.id in bank_anticipated:
            continue
        # rows 1-3: installment
        if tx.installment and tx.amount > 0:
            candidates = _plan_candidates(card_plans, tx, month)
            candidates = [p for p in candidates if (p.id, tx.installment.n) not in used_plans_n]
            if len(candidates) == 1:
                used_plans_n.add((candidates[0].id, tx.installment.n))
                add(tx, _sugg("link_plan", candidates[0].id))
            elif not candidates:
                add(
                    tx,
                    _sugg(
                        "create_plan",
                        None,
                        n=tx.installment.n,
                        of=tx.installment.of,
                        first_invoice_month=add_months(month, -(tx.installment.n - 1)),
                    ),
                )
            else:
                add(tx, _sugg("choose_plan", None, candidates=[p.id for p in candidates]))
                out.statuses[tx.id] = "needs_choice"
            continue
        # row 9: manual provisional (tie -> needs_choice)
        found = _manual_candidates(ctx, tx, used_manuals, card_main=card_main)
        manual = found[0] if len(found) == 1 else None
        if manual is not None:
            used_manuals.add(manual.id)
            add(tx, _sugg("match_manual", manual.id))
        elif found:
            used_manuals.update(m.id for m in found)
            add(tx, _sugg("choose_manual", None, candidates=[m.id for m in found]))
            out.statuses[tx.id] = "needs_choice"
            continue
        # row 10b: recurring purchase
        rec = _match_recurring(ctx, tx, card_main=card_main)
        if rec is not None:
            add(tx, _sugg("link_recurring", rec.id))
            continue
        if manual is not None:
            continue
        # row 11: subscription
        sub = _match_subscription(ctx, tx, month, card_main)
        if sub is not None:
            add(
                tx,
                _sugg(
                    "link_subscription",
                    sub.id,
                    adjust=money_str(tx.amount) if tx.amount != sub.amount_in(month) else None,
                ),
            )
            continue
        # row 15 on invoices (investment charged on the card)
        inv = _match_investment(ctx, tx, account_id=None)
        if inv is not None:
            add(tx, inv)

    # doc-level warnings: rows 7, 8, 10
    matched_n = {
        (s.target_id, t.installment.n)
        for t in lines
        for s in out.suggestions.get(t.id, [])
        if s.type in ("link_plan", "link_anticipation") and t.installment
    }
    for plan in card_plans:
        for charge in schedule(plan):
            if (
                charge.month == month
                and charge.kind == "installment"
                and charge.n is not None
                and (plan.id, charge.n) not in matched_n
                and not _has_bank_ant(out, plan.id)
            ):
                out.warnings.append(f"expected_installment_missing:{plan.id}:{charge.n}")
        ant = plan.anticipation
        if ant and month > ant.target_month:
            for t in lines:
                if (
                    t.installment
                    and t.installment.n >= ant.from_n
                    and any(s.target_id == plan.id for s in out.suggestions.get(t.id, []))
                ):
                    out.warnings.append(f"anticipation_not_happened:{plan.id}")
                    break
    for m in ctx.manuals:
        if (
            ctx.main(m.card_id) == card_main
            and m.invoice_month == month
            and m.id not in used_manuals
        ):
            out.warnings.append(f"unmatched_manual:{m.id}")
    return out


def _installment_clusters(lines: list[Transaction]) -> list[list[Transaction]]:
    """Installment lines of the same purchase: same ``of``, similar description, amount ±2%."""
    clusters: list[list[Transaction]] = []
    for tx in lines:
        if not tx.installment or tx.amount <= 0 or tx.tag == "anticipation_discount":
            continue
        for cluster in clusters:
            head = cluster[0]
            if (
                head.installment
                and head.installment.of == tx.installment.of
                and similarity(head.description, tx.description) >= 0.6
                and _pct_close(tx.amount, head.amount, Decimal(2))
            ):
                cluster.append(tx)
                break
        else:
            clusters.append([tx])
    return clusters


def _has_bank_ant(out: DocResult, plan_id: str) -> bool:
    return any(
        s.type == "bank_anticipation" and s.target_id == plan_id
        for lst in out.suggestions.values()
        for s in lst
    )


def _plan_candidates(
    plans: list[InstallmentPlan], tx: Transaction, month: str
) -> list[InstallmentPlan]:
    assert tx.installment is not None
    out = []
    for p in plans:
        if p.total_installments != tx.installment.of:
            continue
        amount = p.installment_amount or (p.total_amount / p.total_installments)
        if not _close(amount, tx.amount, CENT):
            continue
        if similarity(p.description, tx.description) < 0.8:
            continue
        expected = month_diff(month, p.first_invoice_month) + 1
        if abs(expected - tx.installment.n) > 1:
            continue
        out.append(p)
    return out


def _match_plan(
    plans: list[InstallmentPlan], tx: Transaction, month: str, ignore_n: bool = False
) -> InstallmentPlan | None:
    assert tx.installment is not None
    for p in plans:
        if p.total_installments != tx.installment.of:
            continue
        amount = p.installment_amount or (p.total_amount / p.total_installments)
        if _close(amount, tx.amount, CENT) and similarity(p.description, tx.description) >= 0.8:
            if ignore_n:
                return p
            expected = month_diff(month, p.first_invoice_month) + 1
            if abs(expected - tx.installment.n) <= 1:
                return p
    return None


def _anticipated_plan(
    plans: list[InstallmentPlan], tx: Transaction, month: str
) -> InstallmentPlan | None:
    for p in plans:
        ant = p.anticipation
        if ant is None or ant.target_month != month:
            continue
        if similarity(p.description, tx.description) < 0.6:
            continue
        if (
            tx.installment
            and tx.installment.of == p.total_installments
            and tx.installment.n >= ant.from_n
        ):
            return p
        if tx.tag in ("anticipation", "anticipation_discount"):
            return p
    return None


def _best_plan_for_refund(plans: list[InstallmentPlan], tx: Transaction) -> InstallmentPlan | None:
    best: tuple[float, InstallmentPlan] | None = None
    for p in plans:
        score = similarity(p.description, tx.description)
        if tx.installment and tx.installment.of == p.total_installments:
            score += 0.2
        if score >= 0.8 and (best is None or score > best[0]):
            best = (score, p)
    return best[1] if best else None


def _owner_ok(ctx: ReconContext, a: Transaction, b: Transaction, card_main: str | None) -> bool:
    if card_main is not None:
        return ctx.main(b.card_id) == card_main
    return a.account_id is not None and a.account_id == b.account_id


def _match_manual(
    ctx: ReconContext, tx: Transaction, used: set[str], card_main: str | None
) -> Transaction | None:
    """Row 9 (docs/16 "Casamento previsto × importado"); ``None`` on no match or a tie."""
    found = _manual_candidates(ctx, tx, used, card_main)
    return found[0] if len(found) == 1 else None


def _manual_candidates(
    ctx: ReconContext, tx: Transaction, used: set[str], card_main: str | None
) -> list[Transaction]:
    """Best-scoring manual entries (more than one = tie -> needs_choice)."""
    best: tuple[float, Transaction] | None = None
    tied: list[Transaction] = []
    for m in ctx.manuals:
        if m.id in used or not _owner_ok(ctx, tx, m, card_main):
            continue
        days = abs((m.purchase_date - tx.purchase_date).days)
        if days > 3 or abs(month_diff(m.invoice_month, tx.invoice_month)) > 1:
            continue
        if not _pct_close(tx.amount, m.amount, Decimal(1)):
            continue
        sim = similarity(m.description, tx.description)
        exact = m.amount == tx.amount and days == 0
        if sim < 0.6 and not (exact and sim >= 0.3):
            continue
        score = sim - days * 0.05
        if best is None or score > best[0] + 1e-9:
            best, tied = (score, m), []
        elif abs(score - best[0]) <= 1e-9:
            tied.append(m)
    return [] if best is None else [best[1], *tied]


def _match_recurring(
    ctx: ReconContext, tx: Transaction, card_main: str | None
) -> RecurringPurchase | None:
    """Row 10b (R12.3)."""
    for rec in ctx.recurring:
        if not rec.active:
            continue
        if card_main is not None and ctx.main(rec.card_id) != card_main:
            continue
        if card_main is None and rec.account_id != tx.account_id:
            continue
        desc_ok = (
            bool(
                rec.match_description
                and re.search(rec.match_description, normalize_description(tx.description), re.I)
            )
            or similarity(rec.description, tx.description) >= 0.6
        )
        expected = rec.amount_in(month_of(tx.purchase_date))
        if not desc_ok or not _pct_close(tx.amount, expected, Decimal(20)):
            continue
        tol = tolerance_days(rec)
        upcoming = occurrences(rec, tx.purchase_date + timedelta(days=tol))
        if any(abs((d - tx.purchase_date).days) <= tol for d in upcoming):
            return rec
    return None


def _match_subscription(
    ctx: ReconContext, tx: Transaction, month: str, card_main: str | None
) -> Subscription | None:
    for sub in ctx.subscriptions:
        if card_main is not None and ctx.main(sub.card_id) != card_main:
            continue
        if card_main is None and sub.account_id != tx.account_id:
            continue
        if month < sub.start_month or (sub.end_month and month > sub.end_month):
            continue
        if (
            _pct_close(tx.amount, sub.amount_in(month), Decimal(5))
            and similarity(sub.description, tx.description) >= 0.8
        ):
            return sub
    return None


def _match_investment(
    ctx: ReconContext, tx: Transaction, account_id: str | None
) -> Suggestion | None:
    if tx.tag not in ("investment_contribution", "investment_withdrawal"):
        return None
    movement = "contribution" if tx.tag == "investment_contribution" else "withdrawal"
    open_invs = [i for i in ctx.investments if i.closed_at is None]
    if account_id is not None:
        same = [i for i in open_invs if i.account_id == account_id]
        if len(same) == 1:
            return _sugg("link_investment", same[0].id, movement=movement)
    if len(open_invs) == 1:
        return _sugg("link_investment", open_invs[0].id, movement=movement)
    if open_invs:
        return _sugg(
            "choose_investment", None, candidates=[i.id for i in open_invs], movement=movement
        )
    return None


def reconcile_statement(ctx: ReconContext, lines: list[Transaction], account_id: str) -> DocResult:
    """Rows 9, 10b, 11–15 for a bank statement."""
    out = DocResult()
    used_manuals: set[str] = set()
    acc = ctx.accounts.get(account_id)

    def add(tx: Transaction, s: Suggestion) -> None:
        out.suggestions.setdefault(tx.id, []).append(s)

    advance = _advance_payments(ctx, lines)
    for tx in lines:
        # row 12: invoice payment
        if tx.amount > 0 and (tx.tag == "invoice_payment" or tx.kind is Kind.TRANSFER):
            inv = _match_invoice_payment(ctx, tx, advance)
            if inv is not None:
                add(
                    tx,
                    _sugg(
                        "invoice_payment",
                        inv.path,
                        card_id=inv.card_id,
                        invoice_month=inv.invoice_month,
                    ),
                )
                continue
        # row 15: investments
        s = _match_investment(ctx, tx, account_id)
        if s is not None:
            add(tx, s)
            if s.type == "choose_investment":
                out.statuses[tx.id] = "needs_choice"
            continue
        # row 13: internal transfer between my accounts
        other = _match_internal(ctx, tx)
        if other is not None:
            add(tx, _sugg("internal_transfer", other.id, fingerprint=other.fingerprint))
            continue
        # row 14: money received from a person
        if tx.kind is Kind.INCOME and acc is not None:
            user = _match_alias(ctx, tx.description, exclude=acc.responsible_user_id)
            if user is not None:
                add(tx, _sugg("settlement", user.id, to_user_id=acc.responsible_user_id))
                continue
        if tx.amount <= 0:
            continue
        found = _manual_candidates(ctx, tx, used_manuals, card_main=None)
        manual = found[0] if len(found) == 1 else None
        if manual is not None:
            used_manuals.add(manual.id)
            add(tx, _sugg("match_manual", manual.id))
        elif found:
            used_manuals.update(m.id for m in found)
            add(tx, _sugg("choose_manual", None, candidates=[m.id for m in found]))
            out.statuses[tx.id] = "needs_choice"
            continue
        rec = _match_recurring(ctx, tx, card_main=None)
        if rec is not None:
            add(tx, _sugg("link_recurring", rec.id))
            continue
        if manual is not None:
            continue
        sub = _match_subscription(ctx, tx, tx.invoice_month, None)
        if sub is not None:
            add(tx, _sugg("link_subscription", sub.id))
    if lines:
        start = min(t.purchase_date for t in lines)
        end = max(t.purchase_date for t in lines)
        for m in ctx.manuals:
            if (
                m.account_id == account_id
                and start <= m.purchase_date <= end
                and m.id not in used_manuals
            ):
                out.warnings.append(f"unmatched_manual:{m.id}")
    return out


def _advance_window(inv: InvoiceDoc) -> tuple[date, date] | None:
    if inv.closing_date is None or inv.due_date is None:
        return None
    return inv.closing_date - timedelta(days=31), inv.due_date


def _match_invoice_payment(
    ctx: ReconContext, tx: Transaction, advance: dict[str, InvoiceDoc]
) -> InvoiceDoc | None:
    """Row 12: payment of the amount due around the due date, or an advance payment whose
    sum with the other payments of the period equals ``total − amount_due`` (pre-computed in
    ``advance``)."""
    for inv in ctx.invoices:
        if inv.due_date is None or inv.amount_due is None or inv.amount_due <= 0:
            continue
        if _close(tx.amount, inv.amount_due, CENT) and (
            inv.due_date - timedelta(days=10)
            <= tx.purchase_date
            <= inv.due_date + timedelta(days=7)
        ):
            return inv
    return advance.get(tx.id)


def _advance_payments(ctx: ReconContext, lines: list[Transaction]) -> dict[str, InvoiceDoc]:
    """docs/09 row 12, advance payment: Σ payments of the period = total − amount_due (±0,01)."""
    out: dict[str, InvoiceDoc] = {}
    for inv in ctx.invoices:
        window = _advance_window(inv)
        if window is None or inv.total is None:
            continue
        expected = inv.total - (inv.amount_due or ZERO)
        if expected <= 0:
            continue
        candidates = [
            t
            for t in lines
            if t.tag == "invoice_payment"
            and t.amount > 0
            and t.id not in out
            and window[0] <= t.purchase_date <= window[1]
        ]
        if candidates and _close(sum((t.amount for t in candidates), ZERO), expected, CENT):
            for t in candidates:
                out[t.id] = inv
    return out


def _direction(tx: Transaction) -> int:
    """+1 money out, -1 money in (staging stores income positive, transfers signed)."""
    if tx.kind is Kind.INCOME:
        return -1
    if tx.kind in (Kind.TRANSFER, Kind.SETTLEMENT):
        return 1 if tx.amount > 0 else -1
    return 1 if tx.amount > 0 else -1


def _match_internal(ctx: ReconContext, tx: Transaction) -> Transaction | None:
    """Row 13 (R8.10): same absolute amount, opposite directions, another account of mine."""
    if tx.account_id is None or tx.kind in (Kind.FEE, Kind.REFUND):
        return None
    for other in ctx.other_lines:
        if other.account_id is None or other.account_id == tx.account_id:
            continue
        if abs(other.amount) != abs(tx.amount) or _direction(other) == _direction(tx):
            continue
        if other.kind in (Kind.FEE, Kind.REFUND):
            continue
        if abs((other.purchase_date - tx.purchase_date).days) <= 2:
            return other
    return None


def _match_alias(ctx: ReconContext, description: str, exclude: str) -> User | None:
    norm = normalize_description(description)
    for user in ctx.users.values():
        if user.id == exclude:
            continue
        for alias in user.aliases:
            if alias and normalize_description(alias) in norm:
                return user
    return None


def installment_n_for(plan: InstallmentPlan, month: str) -> int:
    return month_diff(month, plan.first_invoice_month) + 1


__all__ = [
    "DocResult",
    "InvoiceDoc",
    "ReconContext",
    "installment_month",
    "installment_n_for",
    "reconcile_invoice",
    "reconcile_statement",
]
