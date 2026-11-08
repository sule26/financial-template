"""Review actions: edit staged lines, rule suggestions (R5.4), manual-vs-document check (R10.3)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from expense_tracker.domain.allocation import equivalent
from expense_tracker.domain.models import (
    INVOICE_TOTAL_KINDS,
    Allocation,
    Annotation,
    Kind,
    Transaction,
)
from expense_tracker.domain.normalize import normalize_description
from expense_tracker.review.confirm import ReviewError, refresh_status
from expense_tracker.review.reconcile import _match_manual
from expense_tracker.review.staging import recon_context
from expense_tracker.storage import Repository


def _annotation_for(repo: Repository, tx: Transaction, now: datetime) -> Annotation:
    assert tx.fingerprint is not None
    old = repo.get("annotations", tx.fingerprint)
    return old or Annotation(
        fingerprint=tx.fingerprint,
        description=tx.description,
        purchase_date=tx.purchase_date,
        amount=tx.amount,
        owner_id=tx.card_id or tx.account_id,
        updated_at=now,
    )


def edit_staged(
    repo: Repository, tx_id: str, changes: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Edit a staged line. Every edit is stored as an annotation by fingerprint (docs/09)."""
    tx: Transaction | None = repo.get("staging", tx_id)
    if tx is None:
        raise ReviewError("not_found", f"{tx_id} is not in review")
    assert tx.review is not None and tx.fingerprint is not None
    ann = _annotation_for(repo, tx, now)
    update: dict[str, Any] = {}
    ann_update: dict[str, Any] = {"updated_at": now}
    if "category_id" in changes:
        cat = changes["category_id"]
        if cat is not None and repo.get("categories", cat) is None:
            raise ReviewError("reference_not_found", f"category {cat} not found")
        update["category_id"] = cat
        ann_update["category_id"] = cat
    if "allocations" in changes:
        alloc: Allocation | None = changes["allocations"]
        update["allocations"] = alloc
        update["allocation_origin"] = "manual" if alloc is not None else tx.allocation_origin
        ann_update["allocations"] = alloc
    if "kind" in changes and changes["kind"] is not None:
        new_kind = Kind(changes["kind"])
        # R14.8: a card invoice only holds spending (plus investment charged on the card, R9.4).
        if tx.card_id and new_kind not in INVOICE_TOTAL_KINDS:
            raise ReviewError(
                "invalid_kind",
                f"a card invoice line can only be expense, refund, fee or investment, "
                f"not {new_kind.value}",
            )
        update["kind"] = new_kind
        ann_update["kind"] = new_kind
    if "note" in changes:
        update["note"] = changes["note"]
        ann_update["note"] = changes["note"]
    suggestions = list(tx.review.suggestions)
    choices = dict(ann.link_choices)
    if "choose" in changes:  # {"type": ..., "target_id": ...}
        choice = changes["choose"]
        found = False
        for i, s in enumerate(suggestions):
            if s.type == choice["type"]:
                if s.candidates and choice["target_id"] not in s.candidates:
                    raise ReviewError("invalid_choice", "target is not a candidate")
                suggestions[i] = s.model_copy(
                    update={"target_id": choice["target_id"], "rejected": False}
                )
                choices[s.type] = choice["target_id"]
                found = True
        if not found:
            raise ReviewError("invalid_choice", f"no suggestion of type {choice['type']}")
    if "reject" in changes:  # suggestion type
        kind = changes["reject"]
        suggestions = [
            s.model_copy(update={"rejected": True}) if s.type == kind else s for s in suggestions
        ]
        choices[kind] = "rejected"
    if "accept" in changes:
        kind = changes["accept"]
        suggestions = [
            s.model_copy(update={"rejected": False}) if s.type == kind else s for s in suggestions
        ]
        choices.pop(kind, None)
    ann_update["link_choices"] = choices
    status = tx.review.status
    if status == "needs_choice" and not any(
        s.type.startswith("choose_") and not s.target_id and not s.rejected for s in suggestions
    ):
        status = "pending"
    warnings = [w for w in tx.review.warnings if w != "category_missing"]
    new = tx.model_copy(
        update={
            **update,
            "review": tx.review.model_copy(
                update={"suggestions": suggestions, "status": status, "warnings": warnings}
            ),
        }
    )
    if new.category_id is None and new.kind.value in (
        "expense",
        "refund",
        "fee",
        "investment",
        "income",
    ):
        assert new.review is not None
        new = new.model_copy(
            update={
                "review": new.review.model_copy(
                    update={"warnings": [*warnings, "category_missing"]}
                )
            }
        )
    with repo.batch():
        repo.put("staging", new)
        repo.put("annotations", ann.model_copy(update=ann_update))
    return {
        "transaction": new.model_dump(mode="json"),
        "rule_suggestion": rule_suggestion(repo, new),
    }


def rule_suggestion(repo: Repository, tx: Transaction) -> dict[str, Any] | None:
    """R5.4: same edit for the same normalized description in 2 different files."""
    if not tx.fingerprint or not tx.source.sha256:
        return None
    me = repo.get("annotations", tx.fingerprint)
    if me is None or (me.category_id is None and me.allocations is None):
        return None
    desc = normalize_description(tx.description)
    users = {u.id: u for u in repo.all("users")}
    splits = {s.id: s for s in repo.all("split_profiles")}
    lines = {
        t.fingerprint: t for t in [*repo.all("transactions"), *repo.all("staging")] if t.fingerprint
    }
    for other in repo.all("annotations"):
        if other.fingerprint == tx.fingerprint:
            continue
        line = lines.get(other.fingerprint)
        other_desc = normalize_description(other.description or (line.description if line else ""))
        if other_desc != desc:
            continue
        other_sha = (
            line.source.sha256 if line else (other.source_files[0] if other.source_files else None)
        )
        if other_sha is None or other_sha == tx.source.sha256:
            continue
        same_cat = me.category_id is not None and me.category_id == other.category_id
        same_alloc = (
            me.allocations is not None
            and other.allocations is not None
            and equivalent(me.allocations, other.allocations, tx.invoice_month, splits, users)
        )
        if not (same_cat or same_alloc):
            continue
        exists = any(r.when.description_regex == re.escape(desc) for r in repo.all("rules"))
        if exists:
            return None
        priority = max((r.priority for r in repo.all("rules")), default=0) + 10
        return {
            "description_regex": re.escape(desc),
            "priority": priority,
            "category_id": me.category_id if same_cat else None,
            "allocations": (
                me.allocations if isinstance(me.allocations, list) else me.allocations.model_dump()
            )
            if same_alloc and me.allocations is not None
            else None,
        }
    return None


def reconcile_manual(repo: Repository, manual: Transaction, now: datetime) -> dict[str, Any]:
    """R10.3 / docs/07 "Mês em foco": a manual entry in a month that already has its document is
    checked against it immediately."""
    if not manual.provisional or manual.source.type != "manual":
        return {"status": "none"}
    docs = [e for e in repo.all("import_manifest") if e.active and not e.supersedes_candidate]
    if manual.card_id:
        card = repo.get("cards", manual.card_id)
        main = card.parent_card_id or card.id if card else manual.card_id
        doc = next(
            (
                e
                for e in docs
                if e.kind == "fatura"
                and e.card_id == main
                and e.invoice_month == manual.invoice_month
            ),
            None,
        )
    else:
        doc = next(
            (
                e
                for e in docs
                if e.kind == "extrato"
                and e.account_id == manual.account_id
                and e.period_from
                and e.period_to
                and e.period_from <= manual.purchase_date <= e.period_to
            ),
            None,
        )
    if doc is None:
        return {"status": "projected"}
    ctx = recon_context(repo, set())
    ctx.manuals = [manual]
    lines = [
        t
        for t in [*repo.all("transactions"), *repo.all("staging")]
        if t.source.sha256 == doc.sha256 and t.amount > 0
    ]
    taken = {t.fingerprint for t in lines}
    for line in lines:
        card_main = doc.card_id if manual.card_id else None
        if _match_manual(ctx, line, set(), card_main=card_main) is not None:
            assert line.fingerprint is not None
            ann = repo.get("annotations", line.fingerprint) or Annotation(
                fingerprint=line.fingerprint,
                description=line.description,
                purchase_date=line.purchase_date,
                amount=line.amount,
                owner_id=line.card_id or line.account_id,
            )
            ann = ann.model_copy(
                update={
                    "category_id": ann.category_id or manual.category_id,
                    "allocations": ann.allocations
                    or (manual.allocations if manual.allocation_origin == "manual" else None),
                    "note": ann.note or manual.note,
                    "updated_at": now,
                }
            )
            coll = "transactions" if line.review is None else "staging"
            # docs/16: the manual's edits become the line's annotation and win over defaults
            update: dict[str, Any] = {}
            if ann.category_id:
                update["category_id"] = ann.category_id
            if ann.allocations is not None and line.allocation_origin != "manual":
                update["allocations"] = ann.allocations
                update["allocation_origin"] = "manual"
            if ann.note and not line.note:
                update["note"] = ann.note
            with repo.batch():
                repo.put("annotations", ann)
                repo.delete("transactions", manual.id)
                if update:
                    repo.put(coll, line.model_copy(update=update))
                refresh_status(repo, doc.sha256)
            return {"status": "absorbed", "into": line.id, "document": doc.path}
    _ = taken
    return {
        "status": "not_in_document",
        "document": doc.path,
        "message": f"não está no documento {doc.path}",
    }
