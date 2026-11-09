"""Manual transactions, quick entry suggestions and plan actions (R10, R7, R8.7)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from expense_tracker.domain import installments as plans
from expense_tracker.domain.allocation import (
    AllocationError,
    RuleInput,
    apply_precedence,
    resolve_account,
)
from expense_tracker.domain.ledger import Ledger
from expense_tracker.domain.models import (
    Allocation,
    Annotation,
    InstallmentPlan,
    Kind,
    Origin,
    PaymentMethod,
    Source,
    Transaction,
)
from expense_tracker.domain.money import Money
from expense_tracker.domain.months import Month, month_of
from expense_tracker.domain.normalize import normalize_description
from expense_tracker.services.catalog import Catalog
from expense_tracker.services.errors import Invalid, NotFound, new_id
from expense_tracker.services.reports import CATEGORY_KINDS, build_state
from expense_tracker.storage import Repository


class ManualEntry(BaseModel):
    """Payload of the manual / quick entry form (docs/16 "Lançamento rápido")."""

    model_config = {"extra": "forbid"}

    purchase_date: date
    amount: Money
    description: str = Field(min_length=1)
    category_id: str | None = None
    payment_method: PaymentMethod = PaymentMethod.CREDIT
    card_id: str | None = None
    account_id: str | None = None
    allocations: Allocation | None = None
    installments: int = Field(default=1, ge=1, le=120)
    kind: Kind = Kind.EXPENSE
    note: str | None = None
    recurring_purchase_id: str | None = None
    # R14.26: for a conta da casa, the bill month (occurrence month) this entry pays
    recurring_month: Month | None = None
    # R14.26: payment of a conta da casa / subscription; the bill month (default: invoice month)
    subscription_id: str | None = None
    subscription_month: Month | None = None
    # R14.32: which benefit of the benefit card paid it (VR, Home office…)
    benefit_id: str | None = None


class TransactionPatch(BaseModel):
    model_config = {"extra": "forbid"}

    category_id: str | None = None
    allocations: Allocation | None = None
    note: str | None = None
    kind: Kind | None = None
    description: str | None = Field(default=None, min_length=1)
    amount: Money | None = None
    purchase_date: date | None = None
    provisional: bool | None = None
    # R14.23: a manual entry may move to another payment method / card / account
    payment_method: PaymentMethod | None = None
    card_id: str | None = None
    account_id: str | None = None
    benefit_id: str | None = None  # R14.32


@dataclass
class Transactions:
    repo: Repository
    today: date
    now: Callable[[], datetime]
    after_manual_change: Callable[[Transaction], Any] | None = None

    @property
    def catalog(self) -> Catalog:
        return Catalog(self.repo)

    def _ledger(self) -> Ledger:
        return Ledger(build_state(self.repo), self.today)

    # ------------------------------------------------------------ suggestions (R10.2)

    def last_category_for(self, normalized: str) -> str | None:
        best: tuple[date, str] | None = None
        for tx in self.repo.all("transactions"):
            if tx.category_id and normalize_description(tx.description) == normalized:
                key = (tx.purchase_date, tx.category_id)
                if best is None or key > best:
                    best = key
        return best[1] if best else None

    def suggest(
        self,
        description: str,
        amount: Decimal,
        payment_method: PaymentMethod,
        card_id: str | None,
        account_id: str | None,
    ) -> dict[str, Any]:
        ledger = self._ledger()
        own = self._ownership(ledger, payment_method, card_id, account_id)
        d = apply_precedence(
            RuleInput(description, amount, card_id, account_id),
            own,
            self.repo.all("rules"),
            last_category_for=self.last_category_for,
        )
        alloc = d.allocations
        return {
            "category_id": d.category_id,
            "category_origin": d.category_origin,
            "allocations": alloc if isinstance(alloc, list) else alloc.model_dump(),
            "allocation_origin": d.allocation_origin,
            "descriptions": self.known_descriptions(description),
        }

    def known_descriptions(self, prefix: str, limit: int = 8) -> list[str]:
        p = normalize_description(prefix)
        seen: dict[str, None] = {}
        for tx in sorted(
            self.repo.all("transactions"), key=lambda t: t.purchase_date, reverse=True
        ):
            if normalize_description(tx.description).startswith(p) and tx.description not in seen:
                seen[tx.description] = None
            if len(seen) >= limit:
                break
        return list(seen)

    def _ownership(
        self, ledger: Ledger, method: PaymentMethod, card_id: str | None, account_id: str | None
    ) -> Any:
        try:
            if method is PaymentMethod.CREDIT:
                if not card_id:
                    raise Invalid("card_required", "credit entries need card_id")
                return ledger.card_ownership(card_id)
            if not account_id:
                raise Invalid("account_required", "non-credit entries need account_id")
            acc = self.repo.get("accounts", account_id)
            if acc is None:
                raise Invalid("reference_not_found", f"account_id: {account_id}")
            return resolve_account(acc)
        except AllocationError as exc:
            raise Invalid("ownership_unresolved", str(exc)) from exc

    # ------------------------------------------------------------ manual create (R10.1)

    def _check_target(
        self, method: PaymentMethod, card_id: str | None, account_id: str | None
    ) -> None:
        """Same rules as a new manual entry: card for credit, an account of the right type."""
        self._ownership(self._ledger(), method, card_id, account_id)
        if method is PaymentMethod.CREDIT:
            return
        acc = self.repo.get("accounts", account_id or "")
        assert acc is not None  # checked by _ownership
        allowed = {
            "checking": {"debit", "pix", "transfer", "boleto"},
            "benefit": {"benefit"},
            "cash": {"cash"},
        }[acc.type]
        if method.value not in allowed:
            raise Invalid(
                "method_not_allowed", f"{method.value} not allowed on a {acc.type} account"
            )

    def _check_benefit(
        self, method: PaymentMethod, account_id: str | None, benefit_id: str | None
    ) -> None:
        """R14.32: the benefit must be one credited on that benefit card."""
        if benefit_id is None:
            return
        benefit = self.repo.get("benefits", benefit_id)
        if (
            method is not PaymentMethod.BENEFIT
            or benefit is None
            or benefit.destination != "card"
            or benefit.account_id != account_id
        ):
            raise Invalid(
                "invalid_benefit", "benefit_id must be a benefit credited on this benefit card"
            )

    def _default_split(
        self,
        own: Any,
        description: str,
        amount: Any,
        card_id: str | None,
        account_id: str | None,
        category_id: str | None,
    ) -> tuple[Any, str]:
        """R14.16: what "Padrão" resolves to now (docs/08 levels 3–5)."""
        d = apply_precedence(
            RuleInput(description, amount, card_id, account_id),
            own,
            self.repo.all("rules"),
            manual_category=category_id,
        )
        return d.allocations, d.allocation_origin

    def freeze_default_splits(self) -> int:
        """One-off at startup: manual entries saved on "Padrão" before R14.16 get the split they
        show today, so later rules no longer change their months. Returns how many."""
        pending = [
            tx
            for tx in self.repo.all("transactions")
            if tx.source.type == "manual" and tx.allocations is None
        ]
        if not pending:
            return 0
        self.repo.backup(reason="padrao-freeze")  # data migration: keep a copy first
        ledger = self._ledger()
        frozen = 0
        with self.repo.batch():
            for tx in pending:
                try:
                    own = (
                        ledger.card_ownership(tx.card_id)
                        if tx.card_id
                        else ledger.account_ownership(tx.account_id or "")
                    )
                except AllocationError:
                    continue
                alloc, origin = self._default_split(
                    own, tx.description, tx.amount, tx.card_id, tx.account_id, tx.category_id
                )
                self.repo.put(
                    "transactions",
                    tx.model_copy(update={"allocations": alloc, "allocation_origin": origin}),
                )
                frozen += 1
        return frozen

    def create_manual(self, entry: ManualEntry) -> dict[str, Any]:
        cat = self.catalog
        if entry.kind.value in CATEGORY_KINDS and not entry.category_id:
            raise Invalid("category_required", "category is required (R1.11)")
        cat._need("categories", entry.category_id, "category_id")
        cat.check_allocation(entry.allocations)
        cat._need("recurring_purchases", entry.recurring_purchase_id, "recurring_purchase_id")
        cat._need("subscriptions", entry.subscription_id, "subscription_id")
        ledger = self._ledger()
        own = self._ownership(ledger, entry.payment_method, entry.card_id, entry.account_id)
        self._check_benefit(entry.payment_method, entry.account_id, entry.benefit_id)
        # R14.16: "Padrão" is frozen now, like an imported line (rule that matches, else owners),
        # so a rule created later never rewrites months already settled.
        alloc, alloc_origin = (
            (entry.allocations, "manual")
            if entry.allocations is not None
            else self._default_split(own, entry.description, entry.amount, entry.card_id,
                                     entry.account_id, entry.category_id)
        )  # fmt: skip
        if entry.payment_method is PaymentMethod.CREDIT:
            assert entry.card_id is not None
            account_id = None
            month = ledger.month_for_card_date(entry.card_id, entry.purchase_date)
        else:
            if entry.card_id:
                raise Invalid("card_not_allowed", "only credit entries use card_id")
            acc = self.repo.get("accounts", entry.account_id or "")
            assert acc is not None  # checked by _ownership
            allowed = {
                "checking": {"debit", "pix", "transfer", "boleto"},
                "benefit": {"benefit"},
                "cash": {"cash"},
            }[acc.type]
            if entry.payment_method.value not in allowed:
                raise Invalid(
                    "method_not_allowed",
                    f"{entry.payment_method.value} not allowed on a {acc.type} account",
                )
            account_id = entry.account_id
            month = month_of(entry.purchase_date)
        if entry.installments > 1:
            rec_bill = (
                self.repo.get("recurring_purchases", entry.recurring_purchase_id)
                if entry.recurring_purchase_id
                else None
            )
            if entry.subscription_id or (rec_bill is not None and rec_bill.group == "household"):
                raise Invalid(
                    "installments_not_allowed",
                    "a bill/subscription payment is a single entry, not installments",
                )
            if entry.payment_method is not PaymentMethod.CREDIT:
                raise Invalid("installments_credit_only", "installments need a credit card")
            plan = InstallmentPlan(
                id=new_id("plan"),
                origin=Origin(type="manual"),
                card_id=entry.card_id or "",
                description=entry.description,
                total_installments=entry.installments,
                first_invoice_month=month,
                total_amount=entry.amount,
                category_id=entry.category_id,
                allocations=entry.allocations,
            )
            self.repo.put("installment_plans", plan)
            return {"plan": plan.model_dump(mode="json")}
        try:
            tx = Transaction(
                id=new_id("tx"),
                kind=entry.kind,
                source=Source(type="manual"),
                provisional=entry.payment_method is not PaymentMethod.CASH,
                payment_method=entry.payment_method,
                card_id=entry.card_id,
                account_id=account_id,
                purchase_date=entry.purchase_date,
                invoice_month=month,
                description=entry.description,
                amount=entry.amount,
                category_id=entry.category_id,
                allocations=alloc,
                allocation_origin=alloc_origin,
                note=entry.note,
                created_at=self.now(),
                benefit_id=entry.benefit_id,
            )
        except ValidationError as exc:
            raise Invalid("invalid_transaction", str(exc)) from exc
        if entry.recurring_purchase_id:
            rec = self.repo.get("recurring_purchases", entry.recurring_purchase_id)
            assert rec is not None
            link: dict[str, Any] = {"recurring_purchase_id": entry.recurring_purchase_id}
            if rec.group == "household":
                # R14.26: a bill keeps its due-date schedule; the payment marks its month paid
                link["recurring_month"] = entry.recurring_month or month_of(entry.purchase_date)
            else:
                from expense_tracker.domain.recurrence import reanchor

                self.repo.put("recurring_purchases", reanchor(rec, entry.purchase_date))
            tx = tx.model_copy(update={"links": tx.links.model_copy(update=link)})
        if entry.subscription_id:
            # R14.26: this entry pays that subscription's month (its forecast is not repeated)
            tx = tx.model_copy(
                update={
                    "links": tx.links.model_copy(
                        update={
                            "subscription_id": entry.subscription_id,
                            "subscription_month": entry.subscription_month or month,
                        }
                    )
                }
            )
        self.repo.put("transactions", tx)
        reconciliation = self.after_manual_change(tx) if self.after_manual_change else None
        return {"transaction": tx.model_dump(mode="json"), "reconciliation": reconciliation}

    # ------------------------------------------------------------ edit / delete

    def get(self, tx_id: str) -> Transaction:
        tx: Transaction | None = self.repo.get("transactions", tx_id)
        if tx is None:
            raise NotFound("not_found", f"transaction {tx_id} not found")
        return tx

    def update(self, tx_id: str, patch: TransactionPatch) -> Transaction:
        tx = self.get(tx_id)
        changes = patch.model_dump(exclude_unset=True)
        if "category_id" in changes:
            self.catalog._need("categories", changes["category_id"], "category_id")
        if "allocations" in changes:
            self.catalog.check_allocation(patch.allocations)
        kind = changes.get("kind", tx.kind)
        category = changes.get("category_id", tx.category_id)
        if Kind(kind).value in CATEGORY_KINDS and not category:
            raise Invalid("category_required", "choose a category before saving (R1.12)")
        if tx.source.type == "import":
            # Imported values come from the bank; only my edits are allowed (kept as annotation).
            forbidden = {
                "description",
                "amount",
                "purchase_date",
                "provisional",
                "payment_method",
                "card_id",
                "account_id",
            } & changes.keys()
            if forbidden:
                raise Invalid(
                    "imported_readonly",
                    f"imported fields are read-only: {', '.join(sorted(forbidden))}",
                )
        update: dict[str, Any] = {}
        for key in ("category_id", "note", "kind", "description", "amount", "provisional"):
            if key in changes:
                update[key] = getattr(patch, key)
        if "allocations" in changes:
            if patch.allocations is not None:
                update["allocations"] = patch.allocations
                update["allocation_origin"] = "manual"
            else:
                # R14.16: back to "Padrão" = the rule that matches, else the owners (frozen)
                method = PaymentMethod(changes.get("payment_method") or tx.payment_method)
                card = changes.get("card_id", tx.card_id)
                account = changes.get("account_id", tx.account_id)
                own = self._ownership(self._ledger(), method, card, account)
                alloc, origin = self._default_split(
                    own,
                    changes.get("description") or tx.description,
                    patch.amount or tx.amount,
                    card if method is PaymentMethod.CREDIT else None,
                    account if method is not PaymentMethod.CREDIT else None,
                    changes.get("category_id", tx.category_id),
                )
                update["allocations"] = alloc
                update["allocation_origin"] = origin
        moving = {"payment_method", "card_id", "account_id"} & changes.keys()
        if moving:
            method = changes.get("payment_method") or tx.payment_method
            card_id = changes.get("card_id", tx.card_id)
            account_id = changes.get("account_id", tx.account_id)
            method = PaymentMethod(method)
            # credit -> only the card; any other method -> only the account
            card_id, account_id = (
                (card_id, None) if method is PaymentMethod.CREDIT else (None, account_id)
            )
            self._check_target(method, card_id, account_id)
            update.update(payment_method=method, card_id=card_id, account_id=account_id)
            if "benefit_id" not in changes:
                # another card or method: the old benefit no longer applies
                update["benefit_id"] = None
            if "provisional" not in changes:
                # same rule as a new entry: only cash is final right away
                update["provisional"] = method is not PaymentMethod.CASH
        if "benefit_id" in changes:
            self._check_benefit(
                PaymentMethod(update.get("payment_method", tx.payment_method)),
                update.get("account_id", tx.account_id),
                patch.benefit_id,
            )
            update["benefit_id"] = patch.benefit_id
        if moving or ("purchase_date" in changes and patch.purchase_date is not None):
            when = patch.purchase_date or tx.purchase_date
            update["purchase_date"] = when
            card = update.get("card_id", tx.card_id)
            ledger = self._ledger()
            update["invoice_month"] = (
                ledger.month_for_card_date(card, when) if card else month_of(when)
            )
        new = tx.model_copy(update=update)
        new = Transaction.model_validate(new.model_dump(mode="json"))
        with self.repo.batch():
            self.repo.put("transactions", new)
            if tx.fingerprint:
                self._annotate(new)
        if tx.source.type == "manual" and self.after_manual_change is not None:
            self.after_manual_change(new)
        return new

    def _annotate(self, tx: Transaction) -> None:
        assert tx.fingerprint is not None
        old = self.repo.get("annotations", tx.fingerprint)
        ann = Annotation(
            fingerprint=tx.fingerprint,
            category_id=tx.category_id,
            allocations=tx.allocations if tx.allocation_origin == "manual" else None,
            note=tx.note,
            kind=tx.kind,
            link_choices=old.link_choices if old else {},
            source_files=old.source_files if old else [],
            description=tx.description,
            purchase_date=tx.purchase_date,
            amount=tx.amount,
            owner_id=tx.card_id or tx.account_id,
            updated_at=self.now(),
        )
        self.repo.put("annotations", ann)

    def delete(self, tx_id: str) -> dict[str, str]:
        tx = self.get(tx_id)
        if tx.source.type == "import":
            raise Invalid(
                "imported_delete",
                "imported transactions disappear only when the file is removed (R3.4)",
            )
        self.repo.delete("transactions", tx_id)
        return {"deleted": tx_id}

    def recategorize(self, ids: list[str], category_id: str) -> dict[str, int]:
        """Batch recategorization (R1.12 alert action)."""
        self.catalog._need("categories", category_id, "category_id")
        count = 0
        with self.repo.batch():
            for coll in (
                "transactions",
                "installment_plans",
                "subscriptions",
                "recurring_purchases",
            ):
                for item in self.repo.all(coll):
                    if item.id in ids:
                        new = item.model_copy(update={"category_id": category_id})
                        self.repo.put(coll, new)
                        if coll == "transactions" and new.fingerprint:
                            self._annotate(new)
                        count += 1
        return {"updated": count}

    # ------------------------------------------------------------ plans (R7, R8.7)

    def _plan(self, plan_id: str) -> InstallmentPlan:
        plan: InstallmentPlan | None = self.repo.get("installment_plans", plan_id)
        if plan is None:
            raise NotFound("not_found", f"plan {plan_id} not found")
        return plan

    def _imported_months(self, card_id: str) -> set[str]:
        ledger = self._ledger()
        main = ledger.main_card(card_id)
        return {
            e.invoice_month
            for e in self.repo.all("import_manifest")
            if e.active and e.kind == "fatura" and e.card_id == main and e.invoice_month
        }

    def anticipate(
        self, plan_id: str, from_n: int | None, target_month: str | None, amount: Decimal | None
    ) -> InstallmentPlan:
        plan = self._plan(plan_id)
        ledger = self._ledger()
        try:
            new = plans.anticipate(
                plan,
                current_month=ledger.card_h(plan.card_id),
                imported_months=self._imported_months(plan.card_id),
                from_n=from_n,
                target_month=target_month,
                amount=amount,
            )
        except plans.PlanError as exc:
            raise Invalid("plan_error", str(exc)) from exc
        self.repo.put("installment_plans", new)
        return new

    def undo_anticipation(self, plan_id: str) -> InstallmentPlan:
        try:
            new = plans.undo_anticipation(self._plan(plan_id))
        except plans.PlanError as exc:
            raise Invalid("plan_error", str(exc)) from exc
        self.repo.put("installment_plans", new)
        return new

    def anticipated_at_bank(self, plan_id: str, from_n: int) -> InstallmentPlan:
        try:
            new = plans.anticipated_at_bank(self._plan(plan_id), from_n)
        except plans.PlanError as exc:
            raise Invalid("plan_error", str(exc)) from exc
        self.repo.put("installment_plans", new)
        return new

    def cancel_plan(self, plan_id: str, from_n: int) -> InstallmentPlan:
        try:
            new = plans.cancel(self._plan(plan_id), from_n)
        except plans.PlanError as exc:
            raise Invalid("plan_error", str(exc)) from exc
        self.repo.put("installment_plans", new)
        return new

    # ------------------------------------------------------------ reapply rules (docs/08)

    def reapply_rules(self, apply: bool) -> dict[str, Any]:
        """Preview (or apply) re-running rules on confirmed transactions without manual edits."""
        ledger = self._ledger()
        rules = self.repo.all("rules")
        changes = []
        for tx in self.repo.all("transactions"):
            if tx.allocation_origin == "manual":
                continue
            try:
                own = (
                    ledger.card_ownership(tx.card_id)
                    if tx.card_id
                    else ledger.account_ownership(tx.account_id or "")
                )
            except AllocationError:
                continue
            d = apply_precedence(
                RuleInput(tx.description, tx.amount, tx.card_id, tx.account_id), own, rules
            )
            new_cat = d.category_id or tx.category_id
            if d.allocation_origin.startswith("rule:") or new_cat != tx.category_id:
                alloc = d.allocations if d.allocation_origin.startswith("rule:") else tx.allocations
                origin = (
                    d.allocation_origin
                    if d.allocation_origin.startswith("rule:")
                    else tx.allocation_origin
                )
                if alloc == tx.allocations and new_cat == tx.category_id:
                    continue
                changes.append((tx, new_cat, alloc, origin))
        if apply:
            with self.repo.batch():
                for tx, cat_id, alloc, origin in changes:
                    self.repo.put(
                        "transactions",
                        tx.model_copy(
                            update={
                                "category_id": cat_id,
                                "allocations": alloc,
                                "allocation_origin": origin,
                            }
                        ),
                    )
        return {
            "count": len(changes),
            "applied": apply,
            "changes": [
                {
                    "id": tx.id,
                    "description": tx.description,
                    "category_id": cat_id,
                    "allocation_origin": origin,
                }
                for tx, cat_id, _, origin in changes[:200]
            ],
        }
