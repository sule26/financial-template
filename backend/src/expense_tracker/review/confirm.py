"""Confirmation of staged lines and cascade of removed lines (docs/09, docs/05 "Cascata")."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from expense_tracker.domain.documents import ManifestEntry
from expense_tracker.domain.models import (
    Annotation,
    Anticipation,
    InstallmentPlan,
    InstallmentRef,
    Kind,
    Movement,
    Origin,
    Settlement,
    Suggestion,
    Transaction,
)
from expense_tracker.domain.money import ZERO
from expense_tracker.domain.months import add_months
from expense_tracker.domain.normalize import normalize_description
from expense_tracker.domain.recurrence import reanchor
from expense_tracker.review.fingerprint import derived_id
from expense_tracker.storage import Repository

SPENDING_NEED_CATEGORY = ("expense", "refund", "fee", "investment", "income")


class ReviewError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _plan_title(description: str) -> str:
    return normalize_description(description).title() or description


def active_suggestion(tx: Transaction) -> Suggestion | None:
    for s in tx.review.suggestions if tx.review else []:
        if s.rejected:
            continue
        if (
            s.target_id
            or s.type in ("create_plan", "bank_anticipation")
            or (s.type == "link_anticipation_discount" and s.data.get("plan_fingerprint"))
        ):
            return s
    return None


@dataclass
class Confirmer:
    repo: Repository
    now: datetime

    def confirm(self, ids: Iterable[str]) -> dict[str, Any]:
        wanted = list(dict.fromkeys(ids))
        staged = {t.id: t for t in self.repo.all("staging")}
        missing = [i for i in wanted if i not in staged]
        if missing:
            raise ReviewError("not_found", f"not in review: {', '.join(missing[:5])}")
        blocked = []
        for i in wanted:
            tx = staged[i]
            assert tx.review is not None
            if tx.review.status == "overlap":
                blocked.append(f"{i}: overlap")
            elif tx.review.status == "needs_choice" or any(
                s.type.startswith("choose_") and not s.target_id and not s.rejected
                for s in tx.review.suggestions
            ):
                blocked.append(f"{i}: needs_choice")
            elif tx.category_id is None and tx.kind.value in SPENDING_NEED_CATEGORY:
                blocked.append(f"{i}: category_missing")
        if blocked:
            raise ReviewError("cannot_confirm", "; ".join(blocked[:10]))
        shas: set[str] = set()
        with self.repo.batch():
            # plans first, so anticipation/discount lines can reference them
            ordered = sorted((staged[i] for i in wanted), key=self._order)
            for tx in ordered:
                self._confirm_one(tx)
                if tx.source.sha256:
                    shas.add(tx.source.sha256)
            for sha in shas:
                refresh_status(self.repo, sha)
        return {"confirmed": len(wanted)}

    @staticmethod
    def _order(tx: Transaction) -> int:
        """Plans first, then anticipation lines, then discounts (they need the anticipation)."""
        s = active_suggestion(tx)
        rank = {
            "create_plan": 0,
            "bank_anticipation": 1,
            "link_anticipation": 1,
            "link_anticipation_discount": 2,
        }
        return rank.get(s.type, 3) if s else 3

    # ------------------------------------------------------------------ actions

    def _confirm_one(self, tx: Transaction) -> None:
        s = active_suggestion(tx)
        update: dict[str, Any] = {"review": None}
        links = tx.links
        if s is not None:
            handler = getattr(self, f"_do_{s.type}", None)
            if handler is not None:
                result = handler(tx, s)
                if result:
                    links = links.model_copy(update=result.pop("links", {}))
                    update.update(result)
        final = tx.model_copy(update={**update, "links": links})
        final = Transaction.model_validate(final.model_dump(mode="json"))
        self.repo.delete("staging", tx.id)
        self.repo.put("transactions", final)
        self._remember_source(final)

    def _remember_source(self, tx: Transaction) -> None:
        if not tx.fingerprint or not tx.source.sha256:
            return
        ann = self.repo.get("annotations", tx.fingerprint)
        if ann is not None and tx.source.sha256 not in ann.source_files:
            self.repo.put(
                "annotations",
                ann.model_copy(update={"source_files": [*ann.source_files, tx.source.sha256]}),
            )

    def _plan(self, plan_id: str | None, s: Suggestion) -> InstallmentPlan | None:
        if plan_id:
            return self.repo.get("installment_plans", plan_id)
        fp = s.data.get("plan_fingerprint")
        return self.repo.get("installment_plans", derived_id("plan", fp)) if fp else None

    def _do_link_plan(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        assert tx.installment is not None
        return {
            "installment": InstallmentRef(
                plan_id=s.target_id, n=tx.installment.n, of=tx.installment.of
            )
        }

    def _do_create_plan(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        assert tx.installment is not None and tx.fingerprint is not None
        plan_id = derived_id("plan", tx.fingerprint)
        plan = self.repo.get("installment_plans", plan_id)
        if plan is None:
            plan = InstallmentPlan(
                id=plan_id,
                origin=Origin(type="import", fingerprint=tx.fingerprint),
                card_id=tx.card_id or "",
                description=_plan_title(tx.description),
                total_installments=tx.installment.of,
                first_invoice_month=add_months(tx.invoice_month, -(tx.installment.n - 1)),
                total_amount=tx.amount * tx.installment.of,
                installment_amount=tx.amount,
                category_id=tx.category_id,
                allocations=tx.allocations if tx.allocation_origin == "manual" else None,
            )
        elif plan.origin.type == "manual" and plan.origin.fingerprint == tx.fingerprint:
            plan = plan.model_copy(
                update={"origin": Origin(type="import", fingerprint=tx.fingerprint)}
            )
        self.repo.put("installment_plans", plan)
        return {
            "installment": InstallmentRef(plan_id=plan_id, n=tx.installment.n, of=tx.installment.of)
        }

    def _do_refund_plan(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        n = tx.installment.n if tx.installment else 1
        of = tx.installment.of if tx.installment else 1
        plan = self.repo.get("installment_plans", s.target_id)
        if plan is not None:
            of = plan.total_installments
            n = min(n, of)
        return {"installment": InstallmentRef(plan_id=s.target_id, n=n, of=of)}

    def _link_anticipation(
        self, tx: Transaction, plan: InstallmentPlan | None, from_n: int | None
    ) -> dict[str, Any]:
        if plan is None or tx.fingerprint is None:
            return {}
        ant = plan.anticipation
        if ant is None:
            n = from_n or (tx.installment.n if tx.installment else plan.total_installments)
            ant = Anticipation(from_n=n, target_month=tx.invoice_month)
        linked = [*ant.linked_fingerprints]
        if tx.fingerprint not in linked:
            linked.append(tx.fingerprint)
        amount = self._linked_amount(linked, extra=tx)
        plan = plan.model_copy(
            update={
                "anticipation": ant.model_copy(
                    update={"linked_fingerprints": linked, "amount": amount}
                )
            }
        )
        self.repo.put("installment_plans", plan)
        result: dict[str, Any] = {"links": {"anticipation_plan_id": plan.id}}
        if tx.installment:
            result["installment"] = InstallmentRef(
                plan_id=plan.id, n=tx.installment.n, of=tx.installment.of
            )
        return result

    def _linked_amount(self, fps: list[str], extra: Transaction) -> Decimal | None:
        by_fp = {t.fingerprint: t for t in self.repo.all("transactions") if t.fingerprint}
        by_fp[extra.fingerprint] = extra
        total = sum((by_fp[f].amount for f in fps if f in by_fp), ZERO)
        return total if total > 0 else None

    def _do_link_anticipation(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        return self._link_anticipation(tx, self._plan(s.target_id, s), None)

    def _do_link_anticipation_discount(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        return self._link_anticipation(tx, self._plan(s.target_id, s), None)

    def _do_bank_anticipation(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        return self._link_anticipation(tx, self._plan(s.target_id, s), int(s.data["from_n"]))

    def _do_match_manual(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        manual = self.repo.get("transactions", s.target_id)
        if manual is None:
            return {}
        # docs/16: the manual entry is absorbed; my edits become the annotation of the line
        if tx.fingerprint:
            old = self.repo.get("annotations", tx.fingerprint)
            ann = Annotation(
                fingerprint=tx.fingerprint,
                category_id=(old.category_id if old else None) or manual.category_id,
                allocations=(old.allocations if old else None)
                or (manual.allocations if manual.allocation_origin == "manual" else None),
                note=(old.note if old else None) or manual.note,
                description=tx.description,
                purchase_date=tx.purchase_date,
                amount=tx.amount,
                owner_id=tx.card_id or tx.account_id,
                updated_at=self.now,
                source_files=old.source_files if old else [],
            )
            self.repo.put("annotations", ann)
        self.repo.delete("transactions", manual.id)
        result: dict[str, Any] = {}
        if tx.fingerprint:
            saved = self.repo.get("annotations", tx.fingerprint)
            if saved is not None:
                if saved.category_id:
                    result["category_id"] = saved.category_id
                if saved.allocations is not None:
                    result["allocations"] = saved.allocations
                    result["allocation_origin"] = "manual"
                if saved.note:
                    result["note"] = saved.note
        if manual.links.recurring_purchase_id:
            result["links"] = {"recurring_purchase_id": manual.links.recurring_purchase_id}
        return result

    def _do_link_recurring(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        rec = self.repo.get("recurring_purchases", s.target_id)
        if rec is not None and tx.purchase_date > rec.last_date:
            self.repo.put("recurring_purchases", reanchor(rec, tx.purchase_date))
        return {"links": {"recurring_purchase_id": s.target_id}}

    def _do_link_subscription(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        return {"links": {"subscription_id": s.target_id}}

    def _do_invoice_payment(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        entry = self.repo.get("import_manifest", s.target_id)
        if (
            entry is not None
            and tx.fingerprint
            and tx.fingerprint not in entry.paid_by_fingerprints
        ):
            self.repo.put(
                "import_manifest",
                entry.model_copy(
                    update={"paid_by_fingerprints": [*entry.paid_by_fingerprints, tx.fingerprint]}
                ),
            )
        from expense_tracker.domain.models import PaidInvoice

        paid = PaidInvoice(card_id=s.data["card_id"], invoice_month=s.data["invoice_month"])
        return {"kind": Kind.TRANSFER, "category_id": None, "links": {"paid_invoice": paid}}

    def _do_internal_transfer(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        other = self.repo.get("transactions", s.target_id)
        staged_other = None
        if other is None:  # counterpart still in review: mark it too (both become transfers)
            staged_other = next(
                (t for t in self.repo.all("staging") if t.fingerprint == s.data.get("fingerprint")),
                None,
            )
        if staged_other is not None and tx.fingerprint:
            self.repo.put(
                "staging",
                staged_other.model_copy(
                    update={
                        "kind": Kind.TRANSFER,
                        "category_id": None,
                        "links": staged_other.links.model_copy(
                            update={"internal_transfer_fingerprint": tx.fingerprint}
                        ),
                    }
                ),
            )
        if other is not None and tx.fingerprint:
            self.repo.put(
                "transactions",
                other.model_copy(
                    update={
                        "kind": Kind.TRANSFER,
                        "category_id": None,
                        "links": other.links.model_copy(
                            update={"internal_transfer_fingerprint": tx.fingerprint}
                        ),
                    }
                ),
            )
        return {
            "kind": Kind.TRANSFER,
            "category_id": None,
            "links": {"internal_transfer_fingerprint": s.data.get("fingerprint")},
        }

    def _do_settlement(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        assert tx.fingerprint is not None
        sid = derived_id("set", tx.fingerprint)
        existing = self.repo.get("settlements", sid)
        settlement = Settlement(
            id=sid,
            origin=Origin(type="import", fingerprint=tx.fingerprint),
            from_user_id=s.target_id or "",
            to_user_id=s.data["to_user_id"],
            amount=abs(tx.amount),
            date=tx.purchase_date,
            month=tx.invoice_month,
            note=existing.note if existing else tx.description,
        )
        self.repo.put("settlements", settlement)
        return {"kind": Kind.SETTLEMENT, "category_id": None, "links": {"settlement_id": sid}}

    def _do_link_investment(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        inv = self.repo.get("investments", s.target_id)
        if inv is None or tx.fingerprint is None:
            return {}
        movements = [m for m in inv.movements if m.origin.fingerprint != tx.fingerprint]
        movements.append(
            Movement(
                date=tx.purchase_date,
                type=s.data.get("movement", "contribution"),
                amount=abs(tx.amount),
                origin=Origin(type="import", fingerprint=tx.fingerprint),
            )
        )
        self.repo.put("investments", inv.model_copy(update={"movements": movements}))
        kind = Kind.INVESTMENT if tx.card_id else Kind.TRANSFER
        return {"kind": kind, "links": {"investment_id": inv.id}}

    _do_choose_investment = _do_link_investment

    def _do_choose_plan(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        return self._do_link_plan(tx, s)

    def _do_choose_manual(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        return self._do_match_manual(tx, s)

    def _do_apply_annotation(self, tx: Transaction, s: Suggestion) -> dict[str, Any]:
        ann = self.repo.get("annotations", s.target_id)
        if ann is None or tx.fingerprint is None:
            return {}
        self.repo.put("annotations", ann.model_copy(update={"fingerprint": tx.fingerprint}))
        result: dict[str, Any] = {}
        if ann.category_id:
            result["category_id"] = ann.category_id
        if ann.allocations is not None:
            result["allocations"] = ann.allocations
            result["allocation_origin"] = "manual"
        if ann.note:
            result["note"] = ann.note
        return result


def refresh_status(repo: Repository, sha: str) -> None:
    """Manifest status from staged/confirmed lines of the document."""
    entry = next((e for e in repo.all("import_manifest") if e.sha256 == sha and e.active), None)
    if entry is None:
        return
    pending = sum(
        1
        for t in repo.all("staging")
        if t.source.sha256 == sha and (t.review is None or t.review.status != "overlap")
    )
    confirmed = sum(1 for t in repo.all("transactions") if t.source.sha256 == sha)
    if entry.supersedes_candidate:
        status = "pending_review"
    elif pending == 0:
        status = "confirmed"
    elif confirmed == 0:
        status = "pending_review"
    else:
        status = "partially_confirmed"
    if status != entry.status:
        repo.put("import_manifest", entry.model_copy(update={"status": status}))


# ---------------------------------------------------------------------- cascade (R3.13)


def remove_lines(
    repo: Repository, fps: set[str], now: datetime, sha: str | None = None
) -> list[str]:
    """Delete imported lines by fingerprint (only of document ``sha`` when given) and undo/flag
    what was derived from them. Derived objects are touched only for fingerprints that no
    longer exist in any document."""
    if not fps:
        return []
    notices: list[str] = []
    for coll in ("transactions", "staging"):
        for tx in repo.all(coll):
            if tx.fingerprint in fps and (sha is None or tx.source.sha256 == sha):
                repo.delete(coll, tx.id)
    still = {
        t.fingerprint for t in [*repo.all("transactions"), *repo.all("staging")] if t.fingerprint
    }
    fps = fps - still
    if not fps:
        return notices
    remaining = {t.fingerprint: t for t in repo.all("transactions") if t.fingerprint}
    referenced = {
        t.installment.plan_id
        for t in [*repo.all("transactions"), *repo.all("staging")]
        if t.installment and t.installment.plan_id
    }
    for plan in repo.all("installment_plans"):
        changed = plan
        ant = plan.anticipation
        if ant is not None and set(ant.linked_fingerprints) & fps:
            linked = [f for f in ant.linked_fingerprints if f not in fps]
            amount = sum((remaining[f].amount for f in linked if f in remaining), ZERO)
            changed = changed.model_copy(
                update={
                    "anticipation": ant.model_copy(
                        update={
                            "linked_fingerprints": linked,
                            "amount": amount if linked and amount > 0 else None,
                        }
                    )
                }
            )
            if not linked and plan.origin.type == "import" and plan.origin.fingerprint in fps:
                changed = changed.model_copy(update={"anticipation": None})
        if plan.origin.type == "import" and plan.origin.fingerprint in fps:
            if plan.id in referenced:
                pass  # another active line still belongs to the plan
            elif (
                plan.allocations is not None
                or plan.status_override is not None
                or (plan.anticipation is not None and not plan.anticipation.linked_fingerprints)
            ):
                changed = changed.model_copy(
                    update={
                        "origin": Origin(type="manual", fingerprint=plan.origin.fingerprint),
                        "warnings": [*plan.warnings, "origem removida"],
                    }
                )
                notices.append(f"plan {plan.id} kept as manual")
            else:
                repo.delete("installment_plans", plan.id)
                notices.append(f"plan {plan.id} removed")
                continue
        if changed is not plan:
            repo.put("installment_plans", changed)
    for entry in repo.all("import_manifest"):
        if set(entry.paid_by_fingerprints) & fps:
            repo.put(
                "import_manifest",
                entry.model_copy(
                    update={
                        "paid_by_fingerprints": [
                            f for f in entry.paid_by_fingerprints if f not in fps
                        ]
                    }
                ),
            )
    for st in repo.all("settlements"):
        if st.origin.type == "import" and st.origin.fingerprint in fps:
            repo.put(
                "settlements",
                st.model_copy(
                    update={
                        "origin": Origin(type="manual", fingerprint=st.origin.fingerprint),
                        "warnings": [*st.warnings, "origem removida"],
                    }
                ),
            )
            notices.append(f"settlement {st.id} kept as manual")
    for inv in repo.all("investments"):
        changed_mov = False
        movements = []
        for m in inv.movements:
            if m.origin.type == "import" and m.origin.fingerprint in fps:
                m = m.model_copy(
                    update={
                        "origin": Origin(type="manual", fingerprint=m.origin.fingerprint),
                        "warnings": [*m.warnings, "origem removida"],
                    }
                )
                changed_mov = True
            movements.append(m)
        if changed_mov:
            repo.put("investments", inv.model_copy(update={"movements": movements}))
    for tx in repo.all("transactions"):
        if tx.links.internal_transfer_fingerprint in fps:
            repo.put(
                "transactions",
                tx.model_copy(
                    update={
                        "links": tx.links.model_copy(update={"internal_transfer_fingerprint": None})
                    }
                ),
            )
    _ = now
    return notices


def relink_on_return(repo: Repository, fps: set[str]) -> None:
    """When a removed line comes back, objects that became manual are linked again."""
    for st in repo.all("settlements"):
        if st.origin.type == "manual" and st.origin.fingerprint in fps:
            repo.put(
                "settlements",
                st.model_copy(
                    update={
                        "origin": Origin(type="import", fingerprint=st.origin.fingerprint),
                        "warnings": [w for w in st.warnings if w != "origem removida"],
                    }
                ),
            )
    for inv in repo.all("investments"):
        movements = []
        changed = False
        for m in inv.movements:
            if m.origin.type == "manual" and m.origin.fingerprint in fps:
                m = m.model_copy(
                    update={
                        "origin": Origin(type="import", fingerprint=m.origin.fingerprint),
                        "warnings": [w for w in m.warnings if w != "origem removida"],
                    }
                )
                changed = True
            movements.append(m)
        if changed:
            repo.put("investments", inv.model_copy(update={"movements": movements}))


def move_lines(repo: Repository, old_sha: str, new_entry: ManifestEntry, fps: set[str]) -> None:
    """Kept lines of a replaced/altered document now belong to the new document."""
    for coll in ("transactions", "staging"):
        for tx in repo.all(coll):
            if tx.source.sha256 == old_sha and tx.fingerprint in fps:
                repo.put(
                    coll,
                    tx.model_copy(
                        update={
                            "source": tx.source.model_copy(
                                update={"sha256": new_entry.sha256, "path": new_entry.path}
                            )
                        }
                    ),
                )
