"""Description normalization and similarity (docs/04 "Fingerprint", docs/09)."""

from __future__ import annotations

import pytest

from expense_tracker.domain.normalize import normalize_description, similarity, strip_accents


def test_strip_accents() -> None:
    assert strip_accents("Ração Açaí") == "Racao Acai"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Loja X 03/10", "LOJA X"),
        ("Loja X - Parcela 3/10", "LOJA X"),
        ("Loja X (parcela 3 de 10)", "LOJA X"),
        ("ANTECIPADA - Loja X", "LOJA X"),
        ("  padaria   são   joão ", "PADARIA SAO JOAO"),
        ("mercado@centro!", "MERCADO CENTRO"),
        ("PG *UBER TRIP", "PG *UBER TRIP"),
    ],
)
def test_normalize_description(raw: str, expected: str) -> None:
    assert normalize_description(raw) == expected


def test_similarity_identical_after_normalization_is_one() -> None:
    assert similarity("Loja X 01/10", "LOJA X") == 1.0


def test_similarity_empty_is_zero() -> None:
    assert similarity("", "LOJA") == 0.0
    assert similarity("!!!", "LOJA") == 0.0


def test_similarity_partial_is_between_zero_and_one() -> None:
    value = similarity("PETZ CENTRO", "PETZ SHOPPING")
    assert 0.0 < value < 1.0
    assert similarity("PETZ", "ZZZZ AAAA") < 0.6
