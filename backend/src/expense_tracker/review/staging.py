"""Staging of imported lines: identification, defaults, annotations and reconciliation (docs/09)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import Any, Literal

from expense_tracker.domain.allocation import (
    AllocationError,
    LinkedDefaults,
    Ownership,
    RuleInput,
    apply_precedence,
    resolve_account,
    resolve_card,
)
from expense_tracker.domain.documents import CardChoice, ManifestEntry
from expense_tracker.domain.models import (
    INVOICE_TOTAL_KINDS,
    Annotation,
    Card,
    InstallmentRef,
    Kind,
    PaymentMethod,
    ReviewInfo,
    Source,
    Suggestion,
    Transaction,
)
from expense_tracker.domain.months import month_of
from expense_tracker.domain.normalize import folder_key, normalize_description, similarity
from expense_tracker.domain.parse_result import ParseResult, RawLine
from expense_tracker.review.fingerprint import FingerprintInput, fingerprints, tx_id
from expense_tracker.review.reconcile import (
    DocResult,
    InvoiceDoc,
    ReconContext,
    reconcile_invoice,
    reconcile_statement,
)
from expense_tracker.storage import Repository


class OwnerUnresolved(Exception):
    """The card/account of a document could not be identified (``awaiting_card``)."""


@dataclass
class Identified:
    card_id: str | None = None  # main card (invoice) or None
    account_id: str | None = None
    line_cards: list[str] = field(default_factory=list)  # per-line card id (invoices)
    invoice_month: str | None = None
    warnings: list[str] = field(default_factory=list)


def _card_by_digits(cards: list[Card], digits: str | None) -> Card | None:
    if not digits:
        return None
    for card in cards:
        if digits in card.last_digits:
            return card
    return None


FILENAME_MONTH = re.compile(r"(?<!\d)(\d{4})[-_.](0[1-9]|1[0-2])(?!\d)")


def filename_month(path: str) -> str | None:
    """``faturas/inter/2026-10.pdf`` -> ``2026-10`` (operator's naming convention)."""
    m = FILENAME_MONTH.search(PurePosixPath(path).name)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def card_by_folder(cards: list[Card], path: str) -> Card | None:
    """``faturas/<card name>/…``: the folder (case/accents/spaces-insensitive) names the card."""
    parts = PurePosixPath(path).parts
    if len(parts) < 3:
        return None
    key = folder_key(parts[1])
    found = [c for c in cards if not c.parent_card_id and folder_key(c.name) == key]
    return found[0] if len(found) == 1 else None


def account_by_folder(accounts: list[Any], path: str) -> Any | None:
    parts = PurePosixPath(path).parts
    if len(parts) < 3:
        return None
    key = folder_key(parts[1])
    found = [a for a in accounts if folder_key(a.name) == key]
    return found[0] if len(found) == 1 else None


def identify(repo: Repository, entry: ManifestEntry, result: ParseResult) -> Identified:
    """docs/06 "Identificação do cartão ou conta" (raises ``OwnerUnresolved``)."""
    choices: list[CardChoice] = repo.all("card_choices")
    choice = next((c for c in choices if c.sha256 == entry.sha256), None) or next(
        (
            c
            for c in choices
            if c.sha256 is None
            and c.profile_id == result.profile_id
            and c.card_hint == (result.card_hint or result.account_hint)
        ),
        None,
    )
    if result.kind == "extrato":
        accounts = repo.all("accounts")
        acc = next(
            (
                a
                for a in accounts
                if result.account_hint
                and a.account_hint
                and result.account_hint.replace(" ", "") in a.account_hint.replace(" ", "")
            ),
            None,
        )
        if acc is None:
            acc = account_by_folder(accounts, entry.path)
        if acc is None:
            same = [a for a in accounts if a.profile_id == result.profile_id]
            acc = same[0] if len(same) == 1 else None
        if acc is None and choice and choice.account_id:
            acc = repo.get("accounts", choice.account_id)
        if acc is None:
            raise OwnerUnresolved("conta não identificada: escolha a conta deste extrato")
        return Identified(account_id=acc.id)
    cards: list[Card] = repo.all("cards")
    doc_card = _card_by_digits(cards, result.card_hint)
    if doc_card is None:
        doc_card = card_by_folder(cards, entry.path)
    if doc_card is None:
        same = [c for c in cards if c.profile_id == result.profile_id and not c.parent_card_id]
        doc_card = same[0] if len(same) == 1 else None
    if doc_card is None and choice and choice.card_id:
        doc_card = repo.get("cards", choice.card_id)
    if doc_card is None:
        # a line hint may identify the card (invoices without header hint)
        for line in result.lines:
            found = _card_by_digits(cards, line.card_hint)
            if found is not None:
                doc_card = found
                break
    if doc_card is None:
        raise OwnerUnresolved("cartão não identificado: escolha o cartão desta fatura")
    main = doc_card.parent_card_id or doc_card.id
    month = (
        result.invoice_month
        or filename_month(entry.path)
        or (choice.invoice_month if choice else None)
    )
    if month is None:
        raise OwnerUnresolved("mês da fatura não identificado: informe cartão e mês")
    warnings: list[str] = []
    named = filename_month(entry.path)
    if named and result.invoice_month and named != result.invoice_month:
        warnings.append(f"filename_month_differs:{named}")
    line_cards = []
    for line in result.lines:
        card = _card_by_digits(cards, line.card_hint)
        if line.card_hint and card is None:
            tag = f"unknown_card_hint:{line.card_hint}"
            if tag not in warnings:
                warnings.append(tag)
        if card is not None and (card.parent_card_id or card.id) != main:
            card = None
        line_cards.append(card.id if card else main)
    return Identified(card_id=main, line_cards=line_cards, invoice_month=month, warnings=warnings)


def amount_for(line: RawLine, kind: str) -> Decimal:
    if kind in ("expense", "fee", "investment"):
        return abs(line.amount)
    if kind == "refund":
        return -abs(line.amount)
    if kind == "income":
        return abs(line.amount)
    return line.amount  # transfer/settlement keep the signed value (positive = out)


def _method(line: RawLine, repo: Repository, account_id: str | None, kind: str) -> PaymentMethod:
    if account_id is None:
        return PaymentMethod.CREDIT
    if line.payment_method:
        return PaymentMethod(line.payment_method)
    acc = repo.get("accounts", account_id)
    if acc is not None and acc.type == "benefit":
        return PaymentMethod.BENEFIT
    if acc is not None and acc.type == "cash":
        return PaymentMethod.CASH
    return (
        PaymentMethod.TRANSFER
        if kind in ("transfer", "income", "settlement")
        else PaymentMethod.DEBIT
    )


def build_lines(
    repo: Repository, entry: ManifestEntry, result: ParseResult, ident: Identified, now: datetime
) -> list[Transaction]:
    """Turn parsed lines into staging transactions (no defaults yet)."""
    owners = (
        ident.line_cards
        if result.kind == "fatura"
        else [ident.account_id or ""] * len(result.lines)
    )
    inputs = [
        FingerprintInput(
            result.kind,
            owners[i],
            ln.date,
            ln.description,
            ln.amount,
            f"{ln.installment_n}/{ln.installment_of}" if ln.installment_n else "",
        )
        for i, ln in enumerate(result.lines)
    ]
    fps = fingerprints(inputs)
    out = []
    for i, (ln, fp) in enumerate(zip(result.lines, fps, strict=True)):
        kind = ln.kind or "expense"
        is_card = result.kind == "fatura"
        if is_card and Kind(kind) not in INVOICE_TOTAL_KINDS:
            # R14.8: a card invoice review only has spending (and investment, R9.4); the
            # "pagamento recebido" line is the payment seen from the card side — the bank
            # statement already accounts for it (docs/09 row 12), so it is not staged.
            continue
        month = ident.invoice_month if is_card else month_of(ln.date)
        assert month is not None
        income_type = None
        if kind == "income":
            acc = repo.get("accounts", ident.account_id) if ident.account_id else None
            income_type = "benefit" if acc is not None and acc.type == "benefit" else "cash"
        installment = None
        if ln.installment_n and ln.installment_of and ln.installment_n <= ln.installment_of:
            installment = InstallmentRef(n=ln.installment_n, of=ln.installment_of)
        out.append(
            Transaction(
                id=tx_id(f"{fp}|{entry.sha256}"),
                fingerprint=fp,
                kind=Kind(kind),
                source=Source(type="import", sha256=entry.sha256, path=entry.path, line=i),
                provisional=False,
                payment_method=_method(ln, repo, None if is_card else ident.account_id, kind),
                card_id=owners[i] if is_card else None,
                account_id=None if is_card else ident.account_id,
                purchase_date=ln.date,
                invoice_month=month,
                description=ln.description,
                amount=amount_for(ln, kind),
                installment=installment,
                income_type=income_type,  # type: ignore[arg-type]
                tag=ln.tag,
                review=ReviewInfo(),
                created_at=now,
            )
        )
    return out


def recon_context(repo: Repository, exclude_sha: set[str]) -> ReconContext:
    invoices = []
    for e in repo.all("import_manifest"):
        if (
            e.active
            and e.kind == "fatura"
            and e.card_id
            and e.invoice_month
            and not e.supersedes_candidate
        ):
            invoices.append(
                InvoiceDoc(
                    e.path,
                    e.sha256,
                    e.card_id,
                    e.invoice_month,
                    e.total,
                    e.amount_due,
                    e.due_date,
                    e.closing_date,
                )
            )
    imported = [
        t
        for t in [*repo.all("transactions"), *repo.all("staging")]
        if t.source.type == "import" and t.source.sha256 not in exclude_sha
    ]
    return ReconContext(
        cards={c.id: c for c in repo.all("cards")},
        accounts={a.id: a for a in repo.all("accounts")},
        users={u.id: u for u in repo.all("users")},
        plans=repo.all("installment_plans"),
        subscriptions=repo.all("subscriptions"),
        recurring=repo.all("recurring_purchases"),
        investments=repo.all("investments"),
        manuals=[
            t for t in repo.all("transactions") if t.source.type == "manual" and t.provisional
        ],
        invoices=invoices,
        other_lines=imported,
    )


def _ownership(repo: Repository, tx: Transaction) -> Ownership:
    if tx.card_id:
        card = repo.get("cards", tx.card_id)
        if card is None:
            raise AllocationError(f"unknown card {tx.card_id}")
        return resolve_card(
            card, {c.id: c for c in repo.all("cards")}, {a.id: a for a in repo.all("accounts")}
        )
    acc = repo.get("accounts", tx.account_id or "")
    if acc is None:
        raise AllocationError(f"unknown account {tx.account_id}")
    return resolve_account(acc)


def _linked_defaults(repo: Repository, suggestion: Suggestion | None) -> LinkedDefaults | None:
    if suggestion is None or suggestion.target_id is None:
        return None
    if suggestion.type in (
        "link_plan",
        "choose_plan",
        "refund_plan",
        "link_anticipation",
        "link_anticipation_discount",
        "bank_anticipation",
    ):
        plan = repo.get("installment_plans", suggestion.target_id)
        if plan:
            return LinkedDefaults(f"plan:{plan.id}", plan.allocations, plan.category_id)
    if suggestion.type == "link_subscription":
        sub = repo.get("subscriptions", suggestion.target_id)
        if sub:
            return LinkedDefaults(f"subscription:{sub.id}", sub.allocations, sub.category_id)
    if suggestion.type == "link_recurring":
        rec = repo.get("recurring_purchases", suggestion.target_id)
        if rec:
            return LinkedDefaults(f"recurring:{rec.id}", rec.allocations, rec.category_id)
    if suggestion.type in ("match_manual", "choose_manual"):
        manual = repo.get("transactions", suggestion.target_id)
        if manual:
            origin = "manual" if manual.allocation_origin == "manual" else "plan:manual"
            return LinkedDefaults(
                origin,
                manual.allocations if manual.allocation_origin == "manual" else None,
                manual.category_id,
            )
    return None


def last_category_lookup(repo: Repository) -> Callable[[str], str | None]:
    latest: dict[str, tuple[date, str]] = {}
    for tx in repo.all("transactions"):
        if tx.category_id:
            key = normalize_description(tx.description)
            if key not in latest or tx.purchase_date >= latest[key][0]:
                latest[key] = (tx.purchase_date, tx.category_id)
    return lambda d: latest[d][1] if d in latest else None


def apply_defaults(
    repo: Repository, tx: Transaction, last_category: Callable[[str], str | None]
) -> Transaction:
    """Precedence of docs/08 with the annotation (level 1) and the linked object (level 2)."""
    ann: Annotation | None = repo.get("annotations", tx.fingerprint) if tx.fingerprint else None
    suggestions = tx.review.suggestions if tx.review else []
    active = next((s for s in suggestions if not s.rejected and s.target_id), None)
    try:
        own = _ownership(repo, tx)
    except AllocationError:
        return tx
    d = apply_precedence(
        RuleInput(tx.description, tx.amount, tx.card_id, tx.account_id),
        own,
        repo.all("rules"),
        manual_allocations=ann.allocations if ann else None,
        manual_category=ann.category_id if ann else None,
        linked=_linked_defaults(repo, active),
        last_category_for=last_category,
    )
    update: dict[str, Any] = {
        "allocations": d.allocations,
        "allocation_origin": d.allocation_origin,
        "category_id": d.category_id,
    }
    if ann is not None:
        if ann.kind is not None:
            update["kind"] = ann.kind
        if ann.note is not None:
            update["note"] = ann.note
    return tx.model_copy(update=update)


def orphan_suggestion(repo: Repository, tx: Transaction, active_fps: set[str]) -> Suggestion | None:
    """docs/09 "Anotações órfãs"."""
    if tx.fingerprint and repo.get("annotations", tx.fingerprint) is not None:
        return None
    owner = tx.card_id or tx.account_id
    for ann in repo.all("annotations"):
        if ann.fingerprint in active_fps or ann.description is None or ann.amount is None:
            continue
        if ann.owner_id not in (owner, None) or ann.purchase_date is None:
            continue
        if abs((ann.purchase_date - tx.purchase_date).days) > 2:
            continue
        base = max(abs(ann.amount), Decimal("0.01"))
        if abs(abs(ann.amount) - abs(tx.amount)) > base / 100:
            continue
        if similarity(ann.description, tx.description) >= 0.9:
            return Suggestion(type="apply_annotation", target_id=ann.fingerprint)
    return None


def stage_document(
    repo: Repository,
    entry: ManifestEntry,
    result: ParseResult,
    ident: Identified,
    now: datetime,
    only: set[str] | None = None,
) -> tuple[list[Transaction], DocResult]:
    """Build staged lines with suggestions and defaults. ``only`` restricts to fingerprints
    (used by the diff of an altered/replaced document). Returns (lines, doc result)."""
    lines = build_lines(repo, entry, result, ident, now)
    ctx = recon_context(
        repo,
        {entry.sha256} | ({entry.supersedes_candidate} if entry.supersedes_candidate else set()),
    )
    if result.kind == "fatura":
        assert ident.card_id and ident.invoice_month
        recon = reconcile_invoice(ctx, lines, ident.invoice_month, ident.card_id)
    else:
        assert ident.account_id
        recon = reconcile_statement(ctx, lines, ident.account_id)
    active_fps = {
        t.fingerprint for t in [*repo.all("transactions"), *repo.all("staging")] if t.fingerprint
    }
    lookup = last_category_lookup(repo)
    staged = []
    for tx in lines:
        if only is not None and tx.fingerprint not in only:
            continue
        suggestions = list(recon.suggestions.get(tx.id, []))
        ann = repo.get("annotations", tx.fingerprint) if tx.fingerprint else None
        if ann is not None and ann.link_choices:
            suggestions = _apply_link_choices(suggestions, ann.link_choices)
        orphan = orphan_suggestion(repo, tx, active_fps)
        if orphan is not None:
            suggestions.append(orphan)
        status: Literal["pending", "needs_choice", "overlap"] = (
            "needs_choice" if recon.statuses.get(tx.id) == "needs_choice" else "pending"
        )
        if any(s.type.startswith("choose_") and s.target_id for s in suggestions):
            status = "pending"
        warnings = []
        if tx.category_id is None and tx.kind.value in (
            "expense",
            "refund",
            "fee",
            "investment",
            "income",
        ):
            warnings.append("category_missing")
        tx = tx.model_copy(
            update={"review": ReviewInfo(status=status, suggestions=suggestions, warnings=[])}
        )
        tx = apply_defaults(repo, tx, lookup)
        if tx.category_id is None and tx.kind.value in (
            "expense",
            "refund",
            "fee",
            "investment",
            "income",
        ):
            warnings = ["category_missing"]
        else:
            warnings = []
        assert tx.review is not None
        tx = tx.model_copy(update={"review": tx.review.model_copy(update={"warnings": warnings})})
        staged.append(tx)
    return staged, recon


def _apply_link_choices(suggestions: list[Suggestion], choices: dict[str, str]) -> list[Suggestion]:
    """Re-apply choices I made before (needs_choice resolved, suggestion rejected)."""
    out = []
    for s in suggestions:
        choice = choices.get(s.type)
        if choice == "rejected":
            out.append(s.model_copy(update={"rejected": True}))
        elif choice and s.type.startswith("choose_"):
            out.append(s.model_copy(update={"target_id": choice}))
        else:
            out.append(s)
    return out
