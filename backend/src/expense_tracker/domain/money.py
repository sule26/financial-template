"""Money and percentage values (docs/04 "Regras gerais").

Money and percentages are ``Decimal`` in memory and canonical strings with exactly two decimal
places on disk and in the API (``"150.00"``). Floats are rejected everywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
ZERO = Decimal("0.00")


class MoneyError(ValueError):
    """Invalid money or percentage value."""


def parse_decimal(value: Any) -> Decimal:
    """Parse a decimal (str, int or Decimal). Floats are rejected (docs/04 invariant 4)."""
    if isinstance(value, bool):
        raise MoneyError("booleans are not money")
    if isinstance(value, float):
        raise MoneyError("float values are not allowed for money; use a decimal string")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation as exc:
            raise MoneyError(f"invalid decimal: {value!r}") from exc
    else:
        raise MoneyError(f"unsupported money type: {type(value).__name__}")
    if not result.is_finite():
        raise MoneyError(f"invalid decimal: {value!r}")
    return result


def to_money(value: Any) -> Decimal:
    """Parse and quantize to cents (half-even)."""
    return parse_decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)


def money_str(value: Decimal) -> str:
    """Canonical string with exactly two decimals."""
    return f"{value.quantize(CENT, rounding=ROUND_HALF_EVEN):.2f}"


def parse_br_amount(text: str) -> Decimal:
    """Parse a Brazilian formatted amount: ``1.234,56`` -> ``Decimal('1234.56')``."""
    cleaned = text.strip().replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    return to_money(cleaned)


def parse_us_amount(text: str) -> Decimal:
    """Parse a US formatted amount: ``1,234.56`` -> ``Decimal('1234.56')``."""
    cleaned = text.strip().replace("$", "").replace(" ", "").replace(",", "")
    return to_money(cleaned)


def strict_money(value: Any) -> Decimal:
    """Validator for stored/API values: at most two decimal places, never silently rounded."""
    parsed = parse_decimal(value)
    quantized = parsed.quantize(CENT, rounding=ROUND_HALF_EVEN)
    if parsed != quantized:
        raise MoneyError(f"at most 2 decimal places allowed, got {value!r}")
    return quantized


Money = Annotated[
    Decimal, BeforeValidator(strict_money), PlainSerializer(money_str, return_type=str)
]
Pct = Annotated[Decimal, BeforeValidator(strict_money), PlainSerializer(money_str, return_type=str)]


def split_installments(total: Decimal, count: int) -> list[Decimal]:
    """Split ``total`` into ``count`` installments; the first one takes the leftover cents.

    docs/07 "Parcelamentos": 100,00 in 3x -> 33,34 + 33,33 + 33,33.
    """
    if count < 1:
        raise MoneyError("installment count must be >= 1")
    base = (total / count).quantize(CENT, rounding=ROUND_DOWN)
    if total < 0:
        base = -((-total) / count).quantize(CENT, rounding=ROUND_DOWN)
    first = total - base * (count - 1)
    return [first] + [base] * (count - 1)


def allocate_amount(
    amount: Decimal, pcts: Sequence[Decimal], remainder_index: int
) -> list[Decimal]:
    """Split ``amount`` by percentages; cents difference goes to ``remainder_index``.

    docs/08 "Arredondamento": each part is ``amount × pct / 100`` rounded half-even to cents;
    the difference to ``amount`` goes to one designated participant.
    """
    parts = [(amount * p / HUNDRED).quantize(CENT, rounding=ROUND_HALF_EVEN) for p in pcts]
    if parts:
        parts[remainder_index] += amount - sum(parts, ZERO)
    return parts
