"""Fingerprints and deterministic ids (docs/04 "Fingerprint", "Origem de objetos derivados")."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from expense_tracker.domain.money import money_str
from expense_tracker.domain.normalize import normalize_description


@dataclass(frozen=True)
class FingerprintInput:
    source_kind: str  # fatura | extrato
    owner_id: str  # card id (per line) or account id
    purchase_date: date
    description: str
    amount: Decimal
    installment: str  # "n/of" or ""


def _base(item: FingerprintInput) -> str:
    return "|".join(
        [
            item.source_kind,
            item.owner_id,
            item.purchase_date.isoformat(),
            normalize_description(item.description),
            money_str(item.amount),
            item.installment,
        ]
    )


def fingerprints(items: Sequence[FingerprintInput]) -> list[str]:
    """Fingerprint of each item, in document order; identical lines get occurrence 0, 1, 2…"""
    seen: Counter[str] = Counter()
    out = []
    for item in items:
        base = _base(item)
        occurrence = seen[base]
        seen[base] += 1
        digest = hashlib.sha256(f"{base}|{occurrence}".encode()).hexdigest()
        out.append(f"fp_{digest[:40]}")
    return out


def derived_id(prefix: str, fingerprint: str) -> str:
    """Deterministic id of an object created from an imported line (recreated with same id)."""
    return f"{prefix}_{hashlib.sha256(fingerprint.encode()).hexdigest()[:16]}"


def tx_id(fingerprint: str) -> str:
    return derived_id("tx", fingerprint)
