"""Dates with Portuguese month names and year inference (docs/06 "Inferência de ano")."""

from __future__ import annotations

import re
from datetime import date, datetime

PT_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8,
    "set": 9, "out": 10, "nov": 11, "dez": 12,
}  # fmt: skip
_MONTH_TOKEN = re.compile(r"[a-zçã]+", re.I)


def _replace_months(text: str) -> str:
    def sub(m: re.Match[str]) -> str:
        word = m.group(0).lower()
        number = PT_MONTHS.get(word)
        return f"{number:02d}" if number else m.group(0)

    return _MONTH_TOKEN.sub(sub, text)


def _lower_literals(fmt: str) -> str:
    """Lowercase literal characters of a strptime format, keeping ``%X`` directives."""
    return re.sub(r"(%.)|([^%]+)", lambda m: m.group(1) or m.group(2).lower(), fmt)


def parse_date(text: str, fmt: str, month_names: str | None = None) -> tuple[date, bool]:
    """Parse ``text`` with ``fmt``; returns (date, has_year). Without ``%Y``/``%y`` the year is
    a placeholder (2000) and must be inferred with :func:`infer_year`."""
    value = text.strip()
    pattern = fmt
    if month_names == "pt" or "%b" in fmt or "%B" in fmt:
        value = _replace_months(value.lower())
        pattern = _lower_literals(fmt.replace("%b", "%m").replace("%B", "%m"))
    has_year = "%Y" in fmt or "%y" in fmt
    if not has_year:
        value = f"{value} 2000"
        pattern = f"{pattern} %Y"
    parsed = datetime.strptime(value, pattern).date()
    return parsed, has_year


def infer_year(day_month: date, reference: date) -> date:
    """Year such that the date is <= ``reference`` and less than 12 months before it.

    29/02 in a year without it becomes 28/02 of the closest valid year.
    """
    for year in (reference.year, reference.year - 1):
        try:
            candidate = day_month.replace(year=year)
        except ValueError:  # 29/02 in a non-leap year
            candidate = date(year, 2, 28)
        if candidate <= reference:
            return candidate
    return date(reference.year - 1, day_month.month, min(day_month.day, 28))  # pragma: no cover
