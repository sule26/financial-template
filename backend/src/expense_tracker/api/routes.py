"""REST routes for catalog, transactions and reports (docs/12 "API")."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel

from expense_tracker.api.deps import AppContext, ctx
from expense_tracker.domain.models import PaymentMethod
from expense_tracker.domain.money import Money
from expense_tracker.domain.months import Month
from expense_tracker.services.catalog import MODELS
from expense_tracker.services.errors import Invalid
from expense_tracker.services.reports import MarkReceived
from expense_tracker.services.transactions import ManualEntry, TransactionPatch

router = APIRouter(prefix="/api")

PATHS = {
    "users": "users",
    "split-profiles": "split_profiles",
    "accounts": "accounts",
    "cards": "cards",
    "categories": "categories",
    "savings-goals": "savings_goals",
    "subscriptions": "subscriptions",
    "recurring-purchases": "recurring_purchases",
    "installment-plans": "installment_plans",
    "rules": "rules",
    "settlements": "settlements",
    "investments": "investments",
    "benefits": "benefits",
    "institutions": "institutions",
}


def _dump(item: Any) -> Any:
    return item.model_dump(mode="json") if isinstance(item, BaseModel) else item


def _retry_waiting_files(c: AppContext, name: str) -> None:
    """docs/06: registering a card/account (or its finals) retries files waiting for it."""
    if name not in ("cards", "accounts"):
        return
    service = c.extras.get("sync")
    if service is None:
        return
    service.engine.ensure_folders()
    if any(e.status == "awaiting_card" for e in c.repo.all("import_manifest")):
        service.submit(
            "retry_awaiting_card", lambda: service.engine.reprocess_failed(("awaiting_card",))
        )


def _register_crud(path: str, name: str) -> None:
    model = MODELS[name]

    @router.get(f"/{path}", name=f"list_{name}", tags=[path])
    def list_items(c: AppContext = Depends(ctx)) -> list[dict[str, Any]]:
        return [_dump(i) for i in c.catalog.list_items(name)]

    @router.get(f"/{path}/{{item_id}}", name=f"get_{name}", tags=[path])
    def get_item(item_id: str, c: AppContext = Depends(ctx)) -> dict[str, Any]:
        return _dump(c.catalog.get(name, item_id))  # type: ignore[no-any-return]

    @router.post(f"/{path}", name=f"create_{name}", status_code=201, tags=[path])
    def create_item(
        body: dict[str, Any] = Body(..., openapi_examples={"schema": {"value": {}}}),
        c: AppContext = Depends(ctx),
    ) -> dict[str, Any]:
        item = _dump(c.catalog.create(name, body))
        _retry_waiting_files(c, name)
        return item  # type: ignore[no-any-return]

    @router.put(f"/{path}/{{item_id}}", name=f"update_{name}", tags=[path])
    def update_item(
        item_id: str, body: dict[str, Any], c: AppContext = Depends(ctx)
    ) -> dict[str, Any]:
        item = _dump(c.catalog.update(name, item_id, body))
        _retry_waiting_files(c, name)
        return item  # type: ignore[no-any-return]

    @router.delete(f"/{path}/{{item_id}}", name=f"delete_{name}", tags=[path])
    def delete_item(item_id: str, c: AppContext = Depends(ctx)) -> dict[str, Any]:
        return c.catalog.delete(name, item_id)

    _ = model


for _path, _name in PATHS.items():
    _register_crud(_path, _name)


# ---------------------------------------------------------------- transactions


@router.get("/transactions", tags=["transactions"])
def list_transactions(
    month: Month | None = None,
    card_id: str | None = None,
    account_id: str | None = None,
    payment_method: PaymentMethod | None = None,
    uncategorized: bool = False,
    provisional: bool | None = None,
    q: str | None = None,
    c: AppContext = Depends(ctx),
) -> list[dict[str, Any]]:
    out = []
    for tx in c.repo.all("transactions"):
        if month and tx.invoice_month != month:
            continue
        if card_id and tx.card_id != card_id:
            continue
        if account_id and tx.account_id != account_id:
            continue
        if payment_method and tx.payment_method is not payment_method:
            continue
        if uncategorized and tx.category_id is not None:
            continue
        if provisional is not None and tx.provisional != provisional:
            continue
        if q and q.lower() not in tx.description.lower():
            continue
        out.append(tx.model_dump(mode="json"))
    out.sort(key=lambda t: (t["purchase_date"], t["id"]), reverse=True)
    return out


@router.post("/transactions", status_code=201, tags=["transactions"])
def create_transaction(entry: ManualEntry, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    return c.transactions.create_manual(entry)


@router.get("/transactions/suggest", tags=["transactions"])
def suggest(
    description: str,
    payment_method: PaymentMethod = PaymentMethod.CREDIT,
    amount: str = "0",
    card_id: str | None = None,
    account_id: str | None = None,
    c: AppContext = Depends(ctx),
) -> dict[str, Any]:
    try:
        value = Decimal(amount)
    except ArithmeticError as exc:
        raise Invalid("invalid_amount", "amount must be a decimal") from exc
    return c.transactions.suggest(description, value, payment_method, card_id, account_id)


@router.get("/transactions/{tx_id}", tags=["transactions"])
def get_transaction(tx_id: str, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    return c.transactions.get(tx_id).model_dump(mode="json")


@router.patch("/transactions/{tx_id}", tags=["transactions"])
def patch_transaction(
    tx_id: str, patch: TransactionPatch, c: AppContext = Depends(ctx)
) -> dict[str, Any]:
    return c.transactions.update(tx_id, patch).model_dump(mode="json")


@router.delete("/transactions/{tx_id}", tags=["transactions"])
def delete_transaction(tx_id: str, c: AppContext = Depends(ctx)) -> dict[str, str]:
    return c.transactions.delete(tx_id)


class Recategorize(BaseModel):
    ids: list[str]
    category_id: str


@router.post("/transactions/recategorize", tags=["transactions"])
def recategorize(body: Recategorize, c: AppContext = Depends(ctx)) -> dict[str, int]:
    return c.transactions.recategorize(body.ids, body.category_id)


@router.post("/transactions/reapply-rules", tags=["transactions"])
def reapply_rules(apply: bool = False, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    return c.transactions.reapply_rules(apply)


# ---------------------------------------------------------------- plans


class AnticipateBody(BaseModel):
    from_n: int | None = None
    target_month: Month | None = None
    amount: Money | None = None


class CancelBody(BaseModel):
    from_n: int


@router.post("/installment-plans/{plan_id}/anticipate", tags=["installment-plans"])
def anticipate(plan_id: str, body: AnticipateBody, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    plan = c.transactions.anticipate(plan_id, body.from_n, body.target_month, body.amount)
    return plan.model_dump(mode="json")


@router.delete("/installment-plans/{plan_id}/anticipation", tags=["installment-plans"])
def undo_anticipation(plan_id: str, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    return c.transactions.undo_anticipation(plan_id).model_dump(mode="json")


@router.post("/installment-plans/{plan_id}/cancel", tags=["installment-plans"])
def cancel_plan(plan_id: str, body: CancelBody, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    return c.transactions.cancel_plan(plan_id, body.from_n).model_dump(mode="json")


@router.post("/installment-plans/{plan_id}/anticipated-at-bank", tags=["installment-plans"])
def anticipated_at_bank(
    plan_id: str, body: CancelBody, c: AppContext = Depends(ctx)
) -> dict[str, Any]:
    """docs/09 row 7: answer "antecipada no banco" to an expected_installment_missing warning."""
    return c.transactions.anticipated_at_bank(plan_id, body.from_n).model_dump(mode="json")


@router.get("/installment-plans-progress", tags=["installment-plans"])
def plan_progress(c: AppContext = Depends(ctx)) -> dict[str, dict[str, Any]]:
    """R14.19: per plan, status + how many charges and how much is still to come."""
    return c.reports.plan_progress()


@router.get("/installment-plans-status", tags=["installment-plans"])
def plan_statuses(c: AppContext = Depends(ctx)) -> dict[str, str]:
    return c.reports.plan_statuses()


# ---------------------------------------------------------------- recurring actions (R12.4)


class RecurringAction(BaseModel):
    action: str  # postpone | skip | end | resume
    date: dt.date | None = None


@router.post("/recurring-purchases/{rec_id}/action", tags=["recurring-purchases"])
def recurring_action(
    rec_id: str, body: RecurringAction, c: AppContext = Depends(ctx)
) -> dict[str, Any]:
    from expense_tracker.domain import recurrence

    rec = c.catalog.get("recurring_purchases", rec_id)
    if body.action == "postpone":
        if body.date is None:
            raise Invalid("date_required", "postpone needs a date")
        new = recurrence.postpone(rec, body.date)
    elif body.action == "skip":
        if body.date is None:
            raise Invalid("date_required", "skip needs the planned date")
        new = recurrence.skip(rec, body.date)
    elif body.action == "end":
        paid = {m for rid, m in c.reports.ledger().recurring_paid if rid == rec.id}
        new = recurrence.end(rec, c.clock.today(), paid)
    elif body.action == "resume":
        new = recurrence.resume(rec, body.date, c.clock.today())
    else:
        raise Invalid("invalid_action", "action must be postpone, skip, end or resume")
    c.repo.put("recurring_purchases", new)
    return new.model_dump(mode="json")


# ---------------------------------------------------------------- reports


@router.get("/reports/summary", tags=["reports"])
def summary(
    month: Month,
    user_id: str | None = None,
    include_pending: bool = False,
    payment_method: str | None = Query(default=None, pattern="^(credit|benefit|account|cash)$"),
    c: AppContext = Depends(ctx),
) -> dict[str, Any]:
    return c.reports.summary(month, user_id, include_pending, payment_method)


@router.get("/reports/projection", tags=["reports"])
def projection(
    user_id: str | None = None, include_pending: bool = False, c: AppContext = Depends(ctx)
) -> dict[str, Any]:
    return c.reports.projection(user_id, include_pending)


@router.get("/reports/household", tags=["reports"])
def household(month: Month, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    """R14.26: Contas da casa of a month (expected, paid, due date, status)."""
    return c.reports.household(month)


@router.get("/reports/month-items", tags=["reports"])
def month_items(
    month: Month,
    include_pending: bool = False,
    user_id: str | None = None,
    cards_only: bool = False,
    c: AppContext = Depends(ctx),
) -> list[dict[str, Any]]:
    return c.reports.month_items(month, include_pending, user_id, cards_only)


@router.get("/reports/balances", tags=["reports"])
def report_balances(
    user_id: str, include_pending: bool = False, c: AppContext = Depends(ctx)
) -> dict[str, Any]:
    c.catalog.get("users", user_id)
    return c.reports.balances(user_id, include_pending)


@router.get("/reports/receivables", tags=["reports"])
def report_receivables(
    user_id: str, include_pending: bool = False, c: AppContext = Depends(ctx)
) -> dict[str, Any]:
    """R13.11: receivables/payables by counterparty, card or account and invoice due date."""
    c.catalog.get("users", user_id)
    return c.reports.receivables(user_id, include_pending)


@router.post("/reports/receivables/mark-received", status_code=201, tags=["reports"])
def mark_received(body: MarkReceived, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    """R13.16: mark one receivable as received (creates a linked settlement; undo = DELETE it)."""
    return c.reports.mark_received(body).model_dump(mode="json")


@router.get("/reports/investments", tags=["reports"])
def report_investments(c: AppContext = Depends(ctx)) -> dict[str, Any]:
    return c.reports.investments()


@router.get("/alerts", tags=["reports"])
def alerts(c: AppContext = Depends(ctx)) -> list[dict[str, Any]]:
    return c.reports.alerts(c.catalog.uncategorized())


@router.get("/today", tags=["reports"])
def today(c: AppContext = Depends(ctx)) -> dict[str, str]:
    """Server 'today' (docs/07 "Mês em foco": the UI opens on the real current month)."""
    t = c.clock.today()
    return {"date": t.isoformat(), "month": f"{t.year:04d}-{t.month:02d}"}


@router.head("/health", include_in_schema=False)
def health_head() -> Response:
    return Response(status_code=200)
