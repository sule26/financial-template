"""Manifest entries (docs/05 "Manifesto")."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from expense_tracker.domain.documents import (
    ACTIVE_STATUSES,
    STATUS_LABELS,
    CardChoice,
    ManifestEntry,
)
from expense_tracker.domain.ledger import ACTIVE_STATUSES as LEDGER_ACTIVE


def entry(**kw: Any) -> ManifestEntry:
    data: dict[str, Any] = {
        "path": "faturas/x/2026-10.pdf",
        "sha256": "abc",
        "size": 10,
        "mtime": datetime(2026, 10, 1, 12, 0),
        "kind": "fatura",
    }
    data.update(kw)
    return ManifestEntry.model_validate(data)


@pytest.mark.parametrize(
    ("status", "active"),
    [("pending_review", True), ("partially_confirmed", True), ("confirmed", True),
     ("awaiting_card", False), ("superseded", False), ("unknown_profile", False),
     ("error", False), ("duplicate", False)],
)  # fmt: skip
def test_r8_5_active_statuses(status: str, active: bool) -> None:
    assert entry(status=status).active is active
    assert status in STATUS_LABELS


def test_active_statuses_are_the_same_in_ledger_and_manifest() -> None:
    assert frozenset(LEDGER_ACTIVE) == ACTIVE_STATUSES


def test_manifest_defaults_and_validation() -> None:
    e = entry(total="1234.5")
    assert e.status == "pending_review" and e.format == "pdf" and not e.open_invoice
    assert e.model_dump(mode="json")["total"] == "1234.50"
    with pytest.raises(ValidationError):
        entry(status="unknown")
    with pytest.raises(ValidationError):
        entry(invoice_month="2026-13")
    with pytest.raises(ValidationError):
        entry(total=1.5)


def test_card_choice() -> None:
    choice = CardChoice(id="cc", sha256="abc", card_id="card_x", invoice_month="2026-10")
    assert choice.account_id is None
