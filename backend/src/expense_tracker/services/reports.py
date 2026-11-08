"""Build the ledger from storage and expose reports (summary, projection, balances, alerts)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from expense_tracker.domain.allocation import AllocationError, resolve_allocation
from expense_tracker.domain.documents import ManifestEntry
from expense_tracker.domain.installments import status as plan_status
from expense_tracker.domain.investments import contributions_by_goal, evolution, portfolio
from expense_tracker.domain.ledger import (
    DocumentInfo,
    Ledger,
    LedgerItem,
    LedgerState,
    projection_months,
)
from expense_tracker.domain.models import Settlement, Transaction
from expense_tracker.domain.money import ZERO, Money, money_str
from expense_tracker.domain.months import Month, add_months, month_of
from expense_tracker.domain.recurrence import overdue
from expense_tracker.domain.reports import (
    UNCATEGORIZED,
    amount_for,
    balances,
    cards_view,
    committed_income,
    goals_progress,
    receivables,
    summarize,
)
from expense_tracker.services.catalog import Catalog
from expense_tracker.services.errors import Conflict, NotFound
from expense_tracker.storage import Repository

CATEGORY_KINDS = frozenset({"expense", "refund", "fee", "investment", "income"})


class MarkReceived(BaseModel):
    """R13.16: body of ``POST /api/reports/receivables/mark-received``."""

    model_config = {"extra": "forbid"}

    user_id: str
    counterparty_user_id: str
    direction: Literal["receive", "pay"]
    card_id: str | None = None
    account_id: str | None = None
    invoice_month: Month
    amount: Money | None = None  # default: what is still to be received
    include_pending: bool = False


def doc_info(entry: ManifestEntry) -> DocumentInfo:
    return DocumentInfo(
        sha256=entry.sha256,
        kind=entry.kind,
        status=entry.status,
        card_id=entry.card_id,
        account_id=entry.account_id,
        invoice_month=entry.invoice_month,
        open_invoice=entry.open_invoice,
        as_of=entry.as_of,
        period_from=entry.period_from,
        period_to=entry.period_to,
        amount_due=entry.amount_due,
        total=entry.total,
        due_date=entry.due_date,
        closing_date=entry.closing_date,
        paid_by_fingerprints=tuple(entry.paid_by_fingerprints),
        supersedes_candidate=entry.supersedes_candidate,
    )


def build_state(repo: Repository) -> LedgerState:
    return LedgerState(
        users={u.id: u for u in repo.all("users")},
        splits={s.id: s for s in repo.all("split_profiles")},
        cards={c.id: c for c in repo.all("cards")},
        accounts={a.id: a for a in repo.all("accounts")},
        transactions=repo.all("transactions"),
        staging=repo.all("staging"),
        plans=repo.all("installment_plans"),
        subscriptions=repo.all("subscriptions"),
        recurring=repo.all("recurring_purchases"),
        documents=[doc_info(e) for e in repo.all("import_manifest")],
        benefits=repo.all("benefits"),
    )


def _m(value: Decimal | None) -> str | None:
    return None if value is None else money_str(value)


def _dict(values: dict[str, Decimal]) -> dict[str, str]:
    return {k: money_str(v) for k, v in sorted(values.items())}


def item_json(item: LedgerItem, ledger: Ledger) -> dict[str, Any]:
    return {
        "month": item.month,
        "description": item.description,
        "amount": money_str(item.amount),
        "total_amount": money_str(item.amount),
        "kind": item.kind.value,
        "payment_method": item.payment_method.value,
        "origin": item.origin,
        "card_id": item.card_id,
        "account_id": item.account_id,
        "category_id": item.category_id,
        "ref_id": item.ref_id,
        "purchase_date": item.purchase_date.isoformat() if item.purchase_date else None,
        "provisional": item.provisional,
        "forecast": item.is_forecast,
        "parts": _dict(ledger.parts_of(item)),
    }


@dataclass
class Reports:
    repo: Repository
    today: date

    def ledger(self, include_pending: bool = False) -> Ledger:
        return Ledger(build_state(self.repo), self.today, include_pending)

    def summary(
        self,
        month: str,
        user_id: str | None,
        include_pending: bool,
        method: str | None = None,
        months_back: int = 11,
    ) -> dict[str, Any]:
        ledger = self.ledger(include_pending)
        user = self.repo.get("users", user_id) if user_id else None
        months = [add_months(month, -i) for i in range(months_back, -1, -1)]
        views = ledger.months(months)
        series = []
        for view in views:
            s = summarize(ledger, view, user, method)
            series.append(
                {
                    "month": view.month,
                    "total": money_str(s.total),
                    "income": _m(s.income),
                    "benefit_income": _m(s.benefit_income),
                    "by_card": _dict(s.by_card),
                    "by_method": _dict(s.by_method),
                    "states": s.states,
                }
            )
        current = summarize(ledger, views[-1], user, method)
        if user_id:
            keep = self.relevant_owners(ledger, user_id, month) | set(current.by_card)
            current.states = {k: v for k, v in current.states.items() if k in keep}
        year = month[:4]
        annual_views = ledger.months([f"{year}-{m:02d}" for m in range(1, 13)])
        annual: dict[str, dict[str, str]] = {}
        for view in annual_views:
            s = summarize(ledger, view, user, method)
            annual[view.month] = _dict(s.by_category)
        goals = goals_progress(
            self.repo.all("savings_goals"),
            contributions_by_goal(self.repo.all("investments"), month),
        )
        return {
            "month": month,
            "total": money_str(current.total),
            "by_category": _dict(current.by_category),
            "uncategorized_key": UNCATEGORIZED,
            "by_card": _dict(current.by_card),
            "by_method": _dict(current.by_method),
            "states": current.states,
            "series": series,
            "annual": annual,
            "goals": {
                g: {"target": money_str(t), "achieved": money_str(a)} for g, (t, a) in goals.items()
            },
        }

    def relevant_owners(self, ledger: Ledger, user_id: str, month: str) -> set[str]:
        """Cards/accounts where the person is an owner or the responsible."""
        out: set[str] = set()
        users, splits = ledger.s.users, ledger.s.splits
        targets: list[tuple[str, Any]] = []
        for card in ledger.s.cards.values():
            if not card.parent_card_id:
                targets.append((card.id, lambda c=card.id: ledger.card_ownership(c)))
        for acc in ledger.s.accounts.values():
            targets.append((acc.id, lambda a=acc.id: ledger.account_ownership(a)))
        for key, get in targets:
            try:
                own = get()
                shares = resolve_allocation(own.owners, month, splits, users, ledger.s.benefits)
            except AllocationError:
                continue
            if own.responsible_user_id == user_id or any(
                s.user_id == user_id for s in shares.shares
            ):
                out.add(key)
            elif own.responsibles is not None:
                # R14.1: one of several people paying the bank.
                try:
                    payers = resolve_allocation(
                        own.responsibles, month, splits, users, ledger.s.benefits
                    )
                except AllocationError:
                    continue
                if any(s.user_id == user_id for s in payers.shares):
                    out.add(key)
        return out

    def projection(self, user_id: str | None, include_pending: bool) -> dict[str, Any]:
        ledger = self.ledger(include_pending)
        user = self.repo.get("users", user_id) if user_id else None
        months = projection_months(self.today)
        out = []
        for full in ledger.months(months):
            # R14.2: the projection table is about cards only.
            view = cards_view(ledger, full)
            s = summarize(ledger, view, user)
            if user_id:
                keep = self.relevant_owners(ledger, user_id, view.month) | set(s.by_card)
                s.states = {k: v for k, v in s.states.items() if k in keep}
            out.append(
                {
                    "month": view.month,
                    "total": money_str(s.total),
                    "by_card": _dict(s.by_card),
                    "by_category": _dict(s.by_category),
                    "by_method": _dict(s.by_method),
                    "states": s.states,
                }
            )
        commitments = []
        for u in self.repo.all("users"):
            if user_id and u.id != user_id:
                continue
            rows = committed_income(ledger, ledger.months(months), u)
            if any(r.income is not None or r.benefit_income is not None for r in rows):
                commitments.append({"user_id": u.id, "months": [_commit(r) for r in rows]})
        return {"months": out, "committed_income": commitments}

    def month_items(
        self,
        month: str,
        include_pending: bool,
        user_id: str | None = None,
        cards_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Items of a month; ``cards_only`` and ``user_id`` (their part only) for R14.2."""
        if user_id and self.repo.get("users", user_id) is None:
            raise NotFound("not_found", f"user {user_id} not found")
        ledger = self.ledger(include_pending)
        view = ledger.month(month)
        if cards_only:
            view = cards_view(ledger, view)
        out = []
        for item in view.items:
            row = item_json(item, ledger)
            if user_id:
                part = amount_for(ledger, item, user_id)
                if part == ZERO:
                    continue
                row["amount"] = money_str(part)
            out.append(row)
        return out

    def balances(self, user_id: str, include_pending: bool) -> dict[str, Any]:
        ledger = self.ledger(include_pending)
        months = self._history_months()
        views = ledger.months(months)
        bal = balances(ledger, views, self.repo.all("settlements"))
        people = []
        for other in bal.counterparties(user_id):
            per_month = []
            for m in months:
                lines = [
                    ln
                    for ln in bal.lines
                    if ln.month == m and {ln.creditor, ln.debtor} == {user_id, other}
                ]
                sets = [
                    s
                    for s in bal.settlements
                    if s.month == m and {s.from_user_id, s.to_user_id} == {user_id, other}
                ]
                if not lines and not sets:
                    continue
                per_month.append(
                    {
                        "month": m,
                        "net": money_str(bal.net(user_id, other, m)),
                        "incomplete": m in bal.incomplete_months,
                        "lines": [
                            {
                                "ref_id": ln.ref_id,
                                "description": ln.description,
                                "amount": money_str(
                                    ln.amount if ln.creditor == user_id else -ln.amount
                                ),
                                "card_id": ln.card_id,
                                "account_id": ln.account_id,
                                "due_date": ln.due_date.isoformat() if ln.due_date else None,
                            }
                            for ln in lines
                        ],
                        "settlements": [s.model_dump(mode="json") for s in sets],
                    }
                )
            people.append(
                {"user_id": other, "net": money_str(bal.net(user_id, other)), "months": per_month}
            )
        return {
            "user_id": user_id,
            "people": people,
            "incomplete_months": sorted(bal.incomplete_months),
        }

    def receivables(self, user_id: str, include_pending: bool) -> dict[str, Any]:
        """R13.11: what the user receives/pays per counterparty, card or account and month."""
        ledger = self.ledger(include_pending)
        bal = balances(ledger, ledger.months(self._history_months()), self.repo.all("settlements"))
        rows = receivables(bal, user_id, self.today)
        totals = {"receive": ZERO, "pay": ZERO}
        for r in rows:
            totals[r.direction] += r.remaining
        return {
            "user_id": user_id,
            "items": [
                {
                    "counterparty_user_id": r.counterparty_user_id,
                    "direction": r.direction,
                    "card_id": r.card_id,
                    "account_id": r.account_id,
                    "invoice_month": r.invoice_month,
                    "due_date": r.due_date.isoformat() if r.due_date else None,
                    "amount": money_str(r.amount),
                    "settled": money_str(r.settled),
                    "remaining": money_str(r.remaining),
                    "status": r.status,
                    "overdue": r.overdue,
                    "settled_month_total": money_str(r.settled_month_total),
                }
                for r in rows
            ],
            "totals": {k: money_str(v) for k, v in totals.items()},
        }

    def mark_received(self, req: MarkReceived) -> Settlement:
        """R13.16: settle one receivable (its remaining by default) with a linked settlement."""
        catalog = Catalog(self.repo)
        for uid in (req.user_id, req.counterparty_user_id):
            catalog.get("users", uid)
        ledger = self.ledger(req.include_pending)
        card_id = ledger.main_card(req.card_id) if req.card_id else None
        bal = balances(ledger, ledger.months(self._history_months()), self.repo.all("settlements"))
        row = next(
            (
                r
                for r in receivables(bal, req.user_id, self.today)
                if r.counterparty_user_id == req.counterparty_user_id
                and r.direction == req.direction
                and r.card_id == card_id
                and r.account_id == req.account_id
                and r.invoice_month == req.invoice_month
            ),
            None,
        )
        if row is None:
            raise NotFound("receivable_not_found", "no receivable matches this pair/card/month")
        amount = req.amount if req.amount is not None else row.remaining
        if amount <= ZERO:
            raise Conflict("already_received", "this receivable has nothing left to receive")
        payer, payee = (
            (req.counterparty_user_id, req.user_id)
            if req.direction == "receive"
            else (req.user_id, req.counterparty_user_id)
        )
        owner = (
            self.repo.get("cards", card_id)
            if card_id
            else self.repo.get("accounts", req.account_id)
            if req.account_id
            else None
        )
        year, month = req.invoice_month.split("-")
        label = " ".join(
            p for p in ("Recebimento", owner.name if owner else "", f"{month}/{year}") if p
        )
        settlement: Settlement = catalog.create(
            "settlements",
            {
                "from_user_id": payer,
                "to_user_id": payee,
                "amount": money_str(amount),
                "date": self.today.isoformat(),
                "month": req.invoice_month,
                "note": label,
                "card_id": card_id,
                "account_id": req.account_id,
                "invoice_month": req.invoice_month,
            },
        )
        return settlement

    def _history_months(self) -> list[str]:
        txs: Iterable[Transaction] = [*self.repo.all("transactions"), *self.repo.all("staging")]
        months = {t.invoice_month for t in txs}
        months |= {s.month for s in self.repo.all("settlements")}
        current = month_of(self.today)
        if not months:
            return [current]
        start = min(months)
        end = max(max(months), current)
        out = [start]
        while out[-1] < end:
            out.append(add_months(out[-1], 1))
        return out

    def investments(self) -> dict[str, Any]:
        users = {u.id: u for u in self.repo.all("users")}
        splits = {s.id: s for s in self.repo.all("split_profiles")}
        invs = self.repo.all("investments")
        pf = portfolio(invs, self.today, splits, users)
        months = [add_months(month_of(self.today), -i) for i in range(11, -1, -1)]
        return {
            "total": money_str(pf.total),
            "yield_total": money_str(pf.yield_total),
            "by_type": _dict(pf.by_type),
            "by_user": _dict(pf.by_user),
            "positions": [
                {
                    "investment_id": p.investment_id,
                    "balance": money_str(p.balance),
                    "balance_date": p.balance_date.isoformat() if p.balance_date else None,
                    "net_contributions": money_str(p.net_contributions),
                    "yield": _m(p.yield_amount),
                    "stale": p.stale,
                    "estimated": p.estimated,
                }
                for p in pf.positions
            ],
            "evolution": [
                {"month": m, "balance": money_str(b), "contributions": money_str(c)}
                for m, b, c in evolution(invs, months)
            ],
        }

    def plan_statuses(self) -> dict[str, str]:
        ledger = self.ledger()
        out: dict[str, str] = {}
        for plan in self.repo.all("installment_plans"):
            out[plan.id] = plan_status(plan, ledger.card_h(plan.card_id))
        return out

    def alerts(self, uncategorized: dict[str, list[str]]) -> list[dict[str, Any]]:
        """Global banner alerts (docs/03): uncategorized, overdue recurring, missing months,
        files with errors."""
        out: list[dict[str, Any]] = []
        count = sum(len(v) for v in uncategorized.values())
        if count:
            out.append({"type": "uncategorized", "count": count, "items": uncategorized})
        for rec in self.repo.all("recurring_purchases"):
            late = overdue(rec, self.today)
            if late is not None:
                out.append(
                    {
                        "type": "recurring_overdue",
                        "recurring_id": rec.id,
                        "description": rec.description,
                        "planned_date": late.isoformat(),
                    }
                )
        ledger = self.ledger()
        for card in self.repo.all("cards"):
            if card.parent_card_id:
                continue
            h = ledger.card_h(card.id)
            for back in range(1, 4):
                m = add_months(h, -back)
                state, items = ledger.card_month(card.id, m)
                has_activity = any(i.origin != "subscription" for i in items) or any(
                    t.card_id == card.id for t in self.repo.all("transactions")
                )
                if state == "missing" and has_activity:
                    out.append({"type": "missing_invoice", "card_id": card.id, "month": m})
        # consistency: an active file whose lines are all gone makes silent loss visible
        stored = {
            t.source.sha256
            for t in [*self.repo.all("transactions"), *self.repo.all("staging")]
            if t.source.sha256
        }
        empty = [
            e.path
            for e in self.repo.all("import_manifest")
            if e.active and e.tx_fingerprints and e.sha256 not in stored
        ]
        if empty:
            out.append({"type": "inconsistent_files", "count": len(empty), "paths": empty})
        bad = [
            e.path
            for e in self.repo.all("import_manifest")
            if e.status in ("error", "unknown_profile", "awaiting_card")
        ]
        if bad:
            out.append({"type": "files_need_attention", "count": len(bad), "paths": bad})
        return out


def _commit(r: Any) -> dict[str, Any]:
    return {
        "month": r.month,
        "spent": money_str(r.spent),
        "income": _m(r.income),
        "ratio": _m(r.ratio),
        "band": r.band,
        "benefit_spent": money_str(r.benefit_spent),
        "benefit_income": _m(r.benefit_income),
        "benefit_ratio": _m(r.benefit_ratio),
    }


__all__ = ["CATEGORY_KINDS", "ZERO", "Reports", "build_state", "doc_info"]
