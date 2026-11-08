"""Fingerprint and deterministic ids (docs/04 "Fingerprint", "Origem de objetos derivados")."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal

import pytest

from expense_tracker.review.fingerprint import FingerprintInput, derived_id, fingerprints, tx_id


def fi(**over: object) -> FingerprintInput:
    base: dict[str, object] = {
        "source_kind": "fatura",
        "owner_id": "card_a",
        "purchase_date": date(2026, 9, 3),
        "description": "Mercado Bom",
        "amount": Decimal("150.00"),
        "installment": "",
    }
    base.update(over)
    return FingerprintInput(**base)  # type: ignore[arg-type]


def test_r3_12_fingerprint_is_stable_and_prefixed() -> None:
    a = fingerprints([fi()])
    b = fingerprints([fi()])
    assert a == b
    assert re.fullmatch(r"fp_[0-9a-f]{40}", a[0])


def test_r3_12_fingerprint_matches_documented_formula() -> None:
    # docs/04: sha256 of "|"-joined fields incl. canonical amount and occurrence index
    raw = "|".join(["fatura", "card_a", "2026-09-03", "MERCADO BOM", "150.00", "", "0"])
    expected = "fp_" + hashlib.sha256(raw.encode()).hexdigest()[:40]
    assert fingerprints([fi()]) == [expected]


@pytest.mark.parametrize(
    "description",
    ["mercado bom", "  MERCADO   BOM ", "Mércado Bóm"],
)
def test_r3_12_description_is_normalized(description: str) -> None:
    # upper case, no accents, collapsed spaces
    assert fingerprints([fi(description=description)]) == fingerprints([fi()])


def test_r3_12_amount_uses_canonical_form() -> None:
    assert fingerprints([fi(amount=Decimal("150"))]) == fingerprints([fi()])


@pytest.mark.parametrize(
    "field, value",
    [
        ("source_kind", "extrato"),
        ("owner_id", "card_b"),
        ("purchase_date", date(2026, 9, 4)),
        ("description", "Mercado Ruim"),
        ("amount", Decimal("150.01")),
        ("installment", "1/10"),
    ],
)
def test_r3_12_each_identity_field_changes_the_fingerprint(field: str, value: object) -> None:
    assert fingerprints([fi(**{field: value})]) != fingerprints([fi()])


def test_r3_12_identical_lines_get_occurrence_index_in_document_order() -> None:
    other = fi(description="Padaria")
    fps = fingerprints([fi(), other, fi(), fi()])
    assert len(set(fps)) == 4
    # the first, second and third identical line keep their identity across re-imports
    again = fingerprints([fi(), fi(), other, fi()])
    assert again[0] == fps[0]
    assert again[1] == fps[2]
    assert again[3] == fps[3]
    assert again[2] == fps[1]


def test_r3_5_derived_id_is_deterministic_per_fingerprint() -> None:
    fp = fingerprints([fi()])[0]
    pid = derived_id("plan", fp)
    assert pid == derived_id("plan", fp)
    assert pid == "plan_" + hashlib.sha256(fp.encode()).hexdigest()[:16]
    assert derived_id("plan", fp + "x") != pid
    assert derived_id("set", fp).startswith("set_")


def test_r3_5_tx_id_is_derived_from_fingerprint() -> None:
    fp = fingerprints([fi()])[0]
    assert tx_id(fp) == derived_id("tx", fp)
