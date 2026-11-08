"""Apply a bank profile to extracted text or CSV rows (docs/06)."""

from __future__ import annotations

import contextlib
import csv
import io
import re
from datetime import date
from decimal import Decimal
from pathlib import PurePath

from expense_tracker.domain.money import MoneyError, parse_br_amount, parse_us_amount
from expense_tracker.importing.dates import infer_year, parse_date
from expense_tracker.importing.result import ParseResult, RawLine
from expense_tracker.profiles.schema import ClassifyRule, HeaderField, Profile

INVOICE_TOTAL_KINDS = frozenset({"expense", "refund", "fee", "investment"})
MINUS_SIGNS = {"-", "−", "–"}


class ParseError(ValueError):
    """The document does not match the profile in a way that prevents parsing."""


def _amount(text: str, fmt: str) -> Decimal:
    cleaned = text.replace("−", "-").replace("–", "-")
    try:
        return parse_br_amount(cleaned) if fmt == "br" else parse_us_amount(cleaned)
    except MoneyError as exc:
        raise ParseError(f"invalid amount {text!r}") from exc


def detect_pdf(profile: Profile, text: str) -> bool:
    if profile.format != "pdf":
        return False
    return all(s in text for s in profile.detect.all) and not any(
        s in text for s in profile.detect.none
    )


def detect_csv(profile: Profile, header: list[str]) -> bool:
    if profile.format != "csv":
        return False
    names = {h.strip() for h in header}
    return all(c in names for c in profile.detect.columns)


# ------------------------------------------------------------------- header


def _header_value(field: HeaderField, text: str) -> str | None:
    assert field.regex is not None
    m = re.search(field.regex, text, re.M)
    return m.group("v").strip() if m else None


def _header_date(
    field: HeaderField | None, text: str, warnings: list[str], name: str
) -> date | None:
    if field is None:
        return None
    raw = _header_value(field, text)
    if raw is None:
        if not field.optional:
            raise ParseError(f"header {name} not found")
        warnings.append(f"header_missing:{name}")
        return None
    try:
        parsed, has_year = parse_date(raw, field.format or "%d/%m/%Y", field.month_names)
    except ValueError as exc:
        raise ParseError(f"header {name}: cannot parse date {raw!r}") from exc
    if not has_year:
        raise ParseError(f"header {name}: date without year {raw!r}")
    return parsed


def _header_amount(field: HeaderField | None, text: str, fmt: str, name: str) -> Decimal | None:
    if field is None:
        return None
    if field.sum_of is not None:
        total = Decimal("0.00")
        found = False
        for part in field.sum_of:
            m = re.search(part.regex, text, re.M)
            if m is None:
                if part.optional:
                    continue
                return None
            total += _amount(m.group("v"), fmt)
            found = True
        return total if found else None
    raw = _header_value(field, text)
    return _amount(raw, fmt) if raw is not None else None


def _classify(
    rules: list[ClassifyRule], description: str
) -> tuple[str | None, str | None, str | None]:
    kind = tag = method = None
    for rule in rules:
        if re.search(rule.match, description, re.I):
            kind = kind or rule.kind
            tag = tag or rule.tag
            method = method or rule.payment_method
            if kind and tag:
                break
    return kind, tag, method


def _finalize_kind(profile: Profile, amount: Decimal, kind: str | None) -> str:
    if kind:
        return kind
    if amount < 0:
        return profile.tx.negative_means if profile.kind == "fatura" else "income"
    return "expense"


# ------------------------------------------------------------------- PDF text


def parse_text(profile: Profile, pages: list[str], filename: str = "") -> ParseResult:
    """Parse the text of a PDF with a YAML profile."""
    noise = [re.compile(p) for p in profile.page_noise]
    lines: list[str] = []
    for page in pages:
        for ln in page.splitlines():
            stripped = ln.strip()
            if stripped and not any(n.search(stripped) for n in noise):
                lines.append(stripped)
    text = "\n".join(lines)
    full = "\n".join(pages)
    result = _header(profile, full)
    tx = profile.tx
    assert tx.line is not None
    line_re = re.compile(tx.line)
    inst_re = re.compile(tx.installment) if tx.installment else None
    card_re = re.compile(tx.card_section) if tx.card_section else None
    ignore = [re.compile(p) for p in tx.ignore]
    start_re = re.compile(tx.section.start) if tx.section else None
    end_re = re.compile(tx.section.end) if tx.section and tx.section.end else None
    inside = start_re is None
    current_card: str | None = None
    reference = result.closing_date or result.period_to or result.due_date or result.as_of
    for raw in text.split("\n"):
        if start_re is not None and start_re.search(raw):
            inside = True
            continue
        if inside and end_re is not None and end_re.search(raw):
            inside = start_re is None
            continue
        if not inside:
            continue
        if card_re is not None:
            m = card_re.search(raw)
            if m:
                current_card = m.group("v")
                continue
        if any(i.search(raw) for i in ignore):
            result.ignored.append(raw)
            continue
        m = line_re.search(raw)
        if m is None:
            if tx.multiline and result.lines and not re.match(r"^\d", raw):
                last = result.lines[-1]
                result.lines[-1] = last.model_copy(
                    update={"description": f"{last.description} {raw}", "raw": f"{last.raw}\n{raw}"}
                )
            else:
                result.unrecognized.append(raw)
            continue
        groups = m.groupdict()
        amount = _amount(groups["amount"], tx.amount_format)
        sign = (groups.get("sign") or "").strip()
        amount = _signed(abs(amount), sign, tx.sign)
        when = _line_date(groups["date"], tx.date_format, tx.month_names, reference, raw)
        desc = re.sub(r"\s+", " ", groups["desc"]).strip()
        n = of = None
        if groups.get("n") and groups.get("of"):
            n, of = int(groups["n"]), int(groups["of"])
        elif inst_re is not None:
            im = inst_re.search(desc)
            if im:
                n, of = int(im.group("n")), int(im.group("of"))
        kind, tag, method = _classify(profile.classify, desc)
        result.lines.append(
            RawLine(
                index=len(result.lines),
                date=when,
                description=desc,
                amount=amount,
                installment_n=n,
                installment_of=of,
                card_hint=groups.get("card_hint") or current_card,
                kind=_finalize_kind(profile, amount, kind),
                tag=tag,
                payment_method=method,
                raw=raw,
            )
        )
    _finish(profile, result, filename)
    return result


def _signed(amount: Decimal, sign: str, mode: str) -> Decimal:
    """Apply the profile sign convention; result > 0 = money out (docs/06 "Formato").

    - ``auto`` / ``minus_is_credit``: a minus sign marks a credit (refund, payment received)
    - ``plus_is_credit``: a plus sign marks a credit (Inter-like invoices)
    - ``minus_is_debit``: statements printing debits with a minus; unsigned values are credits
    """
    if mode == "plus_is_credit":
        return -amount if sign == "+" else amount
    if mode == "minus_is_debit":
        return amount if sign in MINUS_SIGNS else -amount
    return -amount if sign in MINUS_SIGNS else amount


def _line_date(text: str, fmt: str, names: str | None, reference: date | None, raw: str) -> date:
    try:
        parsed, has_year = parse_date(text, fmt, names)
    except ValueError as exc:
        raise ParseError(f"cannot parse date {text!r} in line {raw!r}") from exc
    if has_year:
        return parsed
    if reference is None:
        raise ParseError("dates without year need a closing/due/period date in the header")
    return infer_year(parsed, reference)


def _header(profile: Profile, text: str) -> ParseResult:
    h = profile.header
    warnings: list[str] = []
    fmt = profile.tx.amount_format
    result = ParseResult(
        kind=profile.kind,
        profile_id=profile.id,
        format=profile.format,
        open_invoice=profile.open_invoice,
    )
    result.due_date = _header_date(h.due_date, text, warnings, "due_date")
    result.closing_date = _header_date(h.closing_date, text, warnings, "closing_date")
    result.period_from = _header_date(h.period_from, text, warnings, "period_from")
    result.period_to = _header_date(h.period_to, text, warnings, "period_to")
    result.as_of = _header_date(h.as_of, text, warnings, "as_of")
    result.total = _header_amount(h.total, text, fmt, "total")
    result.amount_due = _header_amount(h.amount_due, text, fmt, "amount_due")
    if h.card_hint is not None:
        result.card_hint = _header_value(h.card_hint, text)
    if h.account_hint is not None:
        result.account_hint = _header_value(h.account_hint, text)
    result.warnings.extend(warnings)
    return result


def _finish(profile: Profile, result: ParseResult, filename: str) -> None:
    if profile.kind == "fatura":
        if result.due_date is not None:
            result.invoice_month = f"{result.due_date.year:04d}-{result.due_date.month:02d}"
        elif profile.invoice_month_from == "filename" and profile.filename_regex:
            m = re.search(profile.filename_regex, PurePath(filename).name)
            if m:
                result.invoice_month = f"{int(m.group('y')):04d}-{int(m.group('m')):02d}"
        # R4.4 / R4.9: compare purchases with the period total (never with the amount due)
        if result.total is None:
            result.warnings.append("no_total")
        else:
            diff = result.counted_sum(INVOICE_TOTAL_KINDS) - result.total
            if abs(diff) > Decimal("0.01"):
                result.warnings.append(f"sum_mismatch:{diff:.2f}")
    elif result.lines:
        if result.period_from is None:
            result.period_from = min(ln.date for ln in result.lines)
        if result.period_to is None:
            result.period_to = max(ln.date for ln in result.lines)


# ------------------------------------------------------------------- CSV


def read_csv_rows(data: bytes, profile: Profile) -> tuple[list[str], list[list[str]]]:
    assert profile.csv is not None
    spec = profile.csv
    try:
        text = data.decode(spec.encoding)
    except UnicodeDecodeError as exc:
        raise ParseError(f"cannot decode CSV as {spec.encoding}") from exc
    text = text.lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text), delimiter=spec.delimiter))[spec.skip_rows :]
    if not rows:
        return [], []
    if spec.header_row:
        return [c.strip() for c in rows[0]], rows[1:]
    return [], rows


def csv_header(
    data: bytes, encoding_candidates: tuple[str, ...] = ("utf-8-sig", "latin-1")
) -> list[str]:
    """First non-empty row, used for profile detection."""
    for enc in encoding_candidates:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        for delimiter in (";", ",", "\t"):
            rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
            for row in rows[:10]:
                if len(row) > 1:
                    return [c.strip() for c in row]
    return []


def parse_csv(
    profile: Profile, data: bytes, filename: str = "", as_of: date | None = None
) -> ParseResult:
    """Parse a CSV export (open invoices, statements) with a profile (R4.10)."""
    assert profile.csv is not None
    tx = profile.tx
    cols = profile.csv.columns
    header, rows = read_csv_rows(data, profile)
    if not header:
        raise ParseError("CSV header row not found")
    index = {name: i for i, name in enumerate(header)}
    for needed in (cols.date, cols.desc, cols.amount):
        if needed not in index:
            raise ParseError(f"CSV column {needed!r} not found")
    result = ParseResult(
        kind=profile.kind,
        profile_id=profile.id,
        format="csv",
        open_invoice=profile.open_invoice,
        as_of=as_of,
    )
    ignore = [re.compile(p) for p in tx.ignore]
    inst_re = re.compile(r"(?P<n>\d{1,2})\s*(?:/|de)\s*(?P<of>\d{1,2})")
    due_dates: list[date] = []
    reference = as_of or date.today()
    for row in rows:
        if not any(cell.strip() for cell in row):
            continue

        def cell(name: str | None, row: list[str] = row) -> str:
            if name is None or name not in index or index[name] >= len(row):
                return ""
            return row[index[name]].strip()

        desc = re.sub(r"\s+", " ", cell(cols.desc))
        raw = profile.csv.delimiter.join(row)
        if any(i.search(desc) for i in ignore):
            result.ignored.append(raw)
            continue
        try:
            amount = _amount(cell(cols.amount), tx.amount_format)
            when = _line_date(cell(cols.date), tx.date_format, tx.month_names, reference, raw)
        except ParseError:
            result.unrecognized.append(raw)
            continue
        if tx.negative_means == "expense" and profile.kind == "fatura":
            amount = abs(amount)
        n = of = None
        im = inst_re.search(cell(cols.installment)) if cols.installment else None
        if im:
            n, of = int(im.group("n")), int(im.group("of"))
        kind, tag, method = _classify(profile.classify, desc)
        if cols.due_date and cell(cols.due_date):
            with contextlib.suppress(ValueError):
                due_dates.append(parse_date(cell(cols.due_date), tx.date_format)[0])
        result.lines.append(
            RawLine(
                index=len(result.lines),
                date=when,
                description=desc,
                amount=amount,
                installment_n=n,
                installment_of=of,
                card_hint=cell(cols.card_hint) or None,
                kind=_finalize_kind(profile, amount, kind),
                tag=tag,
                payment_method=method,
                raw=raw,
            )
        )
    if due_dates:
        result.due_date = max(due_dates)
    _finish(profile, result, filename)
    return result
