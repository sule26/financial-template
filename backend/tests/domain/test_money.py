"""Money and percentages (docs/04 "Regras gerais", docs/07, docs/08 "Arredondamento")."""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from expense_tracker.domain.money import (
    MoneyError,
    allocate_amount,
    money_str,
    parse_br_amount,
    parse_decimal,
    parse_us_amount,
    split_installments,
    to_money,
)

D = Decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("150.00", D("150.00")), (" -65.5 ", D("-65.5")), (7, D(7)), (D("1.234"), D("1.234"))],
)
def test_parse_decimal_accepts_str_int_and_decimal(raw: object, expected: Decimal) -> None:
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize("raw", [1.5, True, None, [1], "abc", "NaN", "Infinity"])
def test_parse_decimal_rejects_float_bool_garbage_and_non_finite(raw: object) -> None:
    # docs/04 invariant 4: no float ever; also no NaN/inf.
    with pytest.raises(MoneyError):
        parse_decimal(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.005", "1.00"), ("1.015", "1.02"), ("2.5", "2.50"), ("-0.125", "-0.12")],
)
def test_to_money_rounds_half_even_to_cents(raw: str, expected: str) -> None:
    assert to_money(raw) == D(expected)


@pytest.mark.parametrize(
    ("value", "text"), [(D("150"), "150.00"), (D("-65"), "-65.00"), (D("0.005"), "0.00")]
)
def test_money_str_is_canonical_with_two_decimals(value: Decimal, text: str) -> None:
    assert money_str(value) == text


@pytest.mark.parametrize(
    ("text", "expected"), [("1.234,56", "1234.56"), ("R$ 150,00", "150.00"), ("-65,00", "-65.00")]
)
def test_parse_br_amount(text: str, expected: str) -> None:
    assert parse_br_amount(text) == D(expected)


@pytest.mark.parametrize(
    ("text", "expected"), [("1,234.56", "1234.56"), ("$ 150.00", "150.00"), ("-65.00", "-65.00")]
)
def test_parse_us_amount(text: str, expected: str) -> None:
    assert parse_us_amount(text) == D(expected)


def test_r1_2_first_installment_takes_leftover_cents() -> None:
    # docs/07#parcelamentos: 100,00 in 3x -> 33,34 + 33,33 + 33,33
    assert split_installments(D("100.00"), 3) == [D("33.34"), D("33.33"), D("33.33")]


def test_r1_2_single_installment_is_the_total() -> None:
    assert split_installments(D("99.99"), 1) == [D("99.99")]


def test_split_installments_negative_total_keeps_sign() -> None:
    assert split_installments(D("-100.00"), 3) == [D("-33.34"), D("-33.33"), D("-33.33")]


def test_split_installments_rejects_zero_count() -> None:
    with pytest.raises(MoneyError):
        split_installments(D("10.00"), 0)


cents = st.integers(min_value=-10_000_000, max_value=10_000_000).map(lambda c: D(c) / 100)


@given(total=cents, count=st.integers(min_value=1, max_value=120))
def test_r1_2_split_installments_sums_exactly_to_total(total: Decimal, count: int) -> None:
    values = split_installments(total, count)
    assert len(values) == count
    assert sum(values, D("0")) == total
    # all but the first are equal
    assert len(set(values[1:])) <= 1


def test_allocate_amount_gives_cents_difference_to_designated_index() -> None:
    # docs/08#arredondamento: 10,00 by 33,34/33,33/33,33 -> 3,33 each = 9,99; the designated
    # participant takes the missing cent.
    parts = allocate_amount(D("10.00"), [D("33.34"), D("33.33"), D("33.33")], 0)
    assert parts == [D("3.34"), D("3.33"), D("3.33")]
    parts = allocate_amount(D("10.00"), [D("33.34"), D("33.33"), D("33.33")], 2)
    assert parts == [D("3.33"), D("3.33"), D("3.34")]


def test_allocate_amount_empty_pcts_returns_empty() -> None:
    assert allocate_amount(D("10.00"), [], 0) == []


@st.composite
def pct_lists(draw: st.DrawFn) -> list[Decimal]:
    """Lists of 2-decimal percentages summing exactly 100.00."""
    k = draw(st.integers(min_value=1, max_value=6))
    cuts = sorted(draw(st.lists(st.integers(1, 9_999), min_size=k - 1, max_size=k - 1)))
    bounds = [0, *cuts, 10_000]
    values = [b - a for a, b in pairwise(bounds)]
    return [D(v) / 100 for v in values if v > 0] or [D("100.00")]


@given(amount=cents, pcts=pct_lists(), data=st.data())
def test_r6_2_allocation_parts_sum_exactly_to_amount(
    amount: Decimal, pcts: list[Decimal], data: st.DataObject
) -> None:
    idx = data.draw(st.integers(min_value=0, max_value=len(pcts) - 1))
    parts = allocate_amount(amount, pcts, idx)
    assert sum(parts, D("0")) == amount
    assert all(p == p.quantize(D("0.01")) for p in parts)
