"""Parse results produced by profiles and plugins (pipeline contract, docs/06 "Pipeline")."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field

from expense_tracker.domain.money import Money


class RawLine(BaseModel):
    """One recognized line. ``amount > 0`` = money out (charge), ``amount < 0`` = credit."""

    index: int
    date: dt.date
    description: str
    amount: Money
    installment_n: int | None = None
    installment_of: int | None = None
    card_hint: str | None = None
    kind: str | None = None
    tag: str | None = None
    payment_method: str | None = None
    raw: str = ""


class ParseResult(BaseModel):
    kind: str
    profile_id: str
    format: str = "pdf"
    open_invoice: bool = False
    due_date: dt.date | None = None
    closing_date: dt.date | None = None
    total: Money | None = None
    amount_due: Money | None = None
    card_hint: str | None = None
    account_hint: str | None = None
    period_from: dt.date | None = None
    period_to: dt.date | None = None
    as_of: dt.date | None = None
    invoice_month: str | None = None
    lines: list[RawLine] = Field(default_factory=list)
    ignored: list[str] = Field(default_factory=list)
    unrecognized: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def counted_sum(self, counted_kinds: frozenset[str]) -> Decimal:
        """Sum of lines that count towards the invoice total (docs/06 "Conferência")."""
        total = Decimal("0.00")
        for line in self.lines:
            if (line.kind or "expense") in counted_kinds:
                total += line.amount
        return total
