"""Dates with Portuguese month names and year inference (docs/06 "Inferência de ano")."""

from __future__ import annotations

from datetime import date

import pytest

from expense_tracker.importing.dates import infer_year, parse_date


@pytest.mark.parametrize(
    ("text", "fmt", "names", "expected"),
    [
        ("09 de set. 2026", "%d de %b. %Y", "pt", date(2026, 9, 9)),
        ("19 OUT 2026", "%d %b %Y", "pt", date(2026, 10, 19)),
        ("01 DEZ 2026", "%d %b %Y", None, date(2026, 12, 1)),  # %b implies month names
        ("5 de março de 2026", "%d de %B de %Y", "pt", date(2026, 3, 5)),
        ("05 marco 2026", "%d %B %Y", "pt", date(2026, 3, 5)),
        ("14/03/2026", "%d/%m/%Y", None, date(2026, 3, 14)),
        ("14/03/26", "%d/%m/%y", None, date(2026, 3, 14)),
    ],
)
def test_parse_date_with_year(text: str, fmt: str, names: str | None, expected: date) -> None:
    assert parse_date(text, fmt, names) == (expected, True)


def test_parse_date_without_year_reports_missing_year() -> None:
    parsed, has_year = parse_date("10 SET", "%d %b", "pt")
    assert has_year is False
    assert (parsed.day, parsed.month) == (10, 9)


def test_parse_date_without_year_accepts_29_february() -> None:
    parsed, has_year = parse_date("29/02", "%d/%m")
    assert has_year is False
    assert (parsed.day, parsed.month) == (29, 2)


def test_parse_date_invalid_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_date("31/02/2026", "%d/%m/%Y")
    with pytest.raises(ValueError):
        parse_date("10 XYZ 2026", "%d %b %Y", "pt")


def test_infer_year_year_turn_uses_previous_year() -> None:
    # docs/06: fechamento 03/01/2027, linha 28/12 -> 2026
    assert infer_year(date(2000, 12, 28), date(2027, 1, 3)) == date(2026, 12, 28)


def test_infer_year_same_year_when_not_after_reference() -> None:
    assert infer_year(date(2000, 9, 15), date(2026, 10, 10)) == date(2026, 9, 15)
    assert infer_year(date(2000, 10, 10), date(2026, 10, 10)) == date(2026, 10, 10)


def test_infer_year_old_installment_purchase_date() -> None:
    # parcela 8/10 com a data da compra original (14/03) numa fatura de outubro
    assert infer_year(date(2000, 3, 14), date(2026, 10, 10)) == date(2026, 3, 14)


def test_infer_year_29_february_in_leap_year() -> None:
    assert infer_year(date(2000, 2, 29), date(2028, 3, 5)) == date(2028, 2, 29)
    assert infer_year(date(2000, 2, 29), date(2029, 1, 5)) == date(2028, 2, 29)


def test_infer_year_29_february_without_leap_year_still_returns_a_date() -> None:
    result = infer_year(date(2000, 2, 29), date(2027, 3, 5))
    assert result.month == 2
    assert result <= date(2027, 3, 5)


def test_infer_year_29_february_fallback_stays_within_12_months() -> None:
    reference = date(2027, 3, 5)
    result = infer_year(date(2000, 2, 29), reference)
    assert date(2026, 3, 5) < result <= reference
