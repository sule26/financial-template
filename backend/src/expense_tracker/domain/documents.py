"""Imported documents (manifest entries) and parse results (docs/05 "Manifesto")."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field

from expense_tracker.domain.models import Model
from expense_tracker.domain.money import Money
from expense_tracker.domain.months import Month

FileStatus = Literal[
    "pending_review",
    "partially_confirmed",
    "confirmed",
    "awaiting_card",
    "superseded",
    "unknown_profile",
    "error",
    "duplicate",
]

ACTIVE_STATUSES: frozenset[str] = frozenset({"pending_review", "partially_confirmed", "confirmed"})

STATUS_LABELS: dict[str, str] = {
    "pending_review": "pendente revisão",
    "partially_confirmed": "parcialmente confirmado",
    "confirmed": "confirmado",
    "awaiting_card": "aguardando cartão",
    "superseded": "substituído",
    "unknown_profile": "perfil desconhecido",
    "error": "erro",
    "duplicate": "duplicado",
}


class ManifestEntry(Model):
    path: str
    sha256: str
    size: int
    mtime: dt.datetime
    kind: Literal["fatura", "extrato"]
    format: Literal["pdf", "csv"] = "pdf"
    profile_id: str | None = None
    card_id: str | None = None
    account_id: str | None = None
    invoice_month: Month | None = None
    closing_date: dt.date | None = None
    due_date: dt.date | None = None
    total: Money | None = None
    amount_due: Money | None = None
    open_invoice: bool = False
    as_of: dt.date | None = None
    period_from: dt.date | None = None
    period_to: dt.date | None = None
    status: FileStatus = "pending_review"
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    duplicate_of: str | None = None
    superseded_by: str | None = None
    supersedes: str | None = None
    supersedes_candidate: str | None = None
    paid_by_fingerprints: list[str] = Field(default_factory=list)
    tx_fingerprints: list[str] = Field(default_factory=list)
    card_hint: str | None = None
    imported_at: dt.datetime | None = None

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class CardChoice(Model):
    """Remembered card/account choice for files that could not be identified (R4.8)."""

    id: str
    sha256: str | None = None
    profile_id: str | None = None
    card_hint: str | None = None
    card_id: str | None = None
    account_id: str | None = None
    invoice_month: Month | None = None
