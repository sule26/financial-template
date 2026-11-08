"""CSV exports and open invoices (docs/06 "Fatura aberta e formatos tabulares", R4.10, R4.11)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import yaml

from expense_tracker.importing import ParseError, parse_csv
from expense_tracker.importing.parser import csv_header, read_csv_rows
from expense_tracker.profiles import Profile, parse_profile
from fixtures.files import OPEN_INVOICE_CSV_PROFILE, open_invoice_csv

AS_OF = date(2026, 10, 18)


def profile(**overrides: object) -> Profile:
    data = yaml.safe_load(OPEN_INVOICE_CSV_PROFILE)
    for key, value in overrides.items():
        if key == "csv":
            data["csv"] = {**data["csv"], **value}  # type: ignore[dict-item]
        else:
            data[key] = value
    return parse_profile(yaml.safe_dump(data, allow_unicode=True))


ROWS = [
    ("01/10/2026", "LOJA A", "100,00", ""),
    ("02/10/2026", "LOJA B PARCELADA", "50,00", "1/3"),
    ("03/10/2026", "ESTORNO LOJA", "-10,00", ""),
]


def test_r4_10_open_invoice_csv_is_parsed() -> None:
    result = parse_csv(profile(), open_invoice_csv(ROWS), "fatura-2026-10.csv", as_of=AS_OF)
    assert result.format == "csv"
    assert result.open_invoice is True
    assert result.as_of == AS_OF
    assert result.invoice_month == "2026-10"
    assert [ln.date for ln in result.lines] == [date(2026, 10, d) for d in (1, 2, 3)]
    assert [ln.amount for ln in result.lines] == [
        Decimal("100.00"),
        Decimal("50.00"),
        Decimal("-10.00"),
    ]
    assert [ln.kind for ln in result.lines] == ["expense", "expense", "refund"]
    assert result.unrecognized == []


def test_r4_11_utf8_bom_does_not_break_first_column() -> None:
    data = open_invoice_csv(ROWS)
    assert data.startswith(b"\xef\xbb\xbf")
    header, rows = read_csv_rows(data, profile())
    assert header[0] == "Data"
    assert len(rows) == 3
    # also with plain utf-8 encoding declared (BOM is accepted, docs/06)
    plain = profile(csv={"encoding": "utf-8"})
    assert parse_csv(plain, data, "f-2026-10.csv").lines[0].description == "LOJA A"


def test_r4_6_csv_installment_slash_and_de_forms() -> None:
    rows = [("02/10/2026", "LOJA", "50,00", "1/3"), ("02/10/2026", "OUTRA", "10,00", "3 de 10")]
    result = parse_csv(profile(), open_invoice_csv(rows), "f-2026-10.csv")
    assert [(ln.installment_n, ln.installment_of) for ln in result.lines] == [(1, 3), (3, 10)]


def test_r4_10_csv_has_no_total_check() -> None:
    result = parse_csv(profile(), open_invoice_csv(ROWS), "f-2026-10.csv")
    assert "no_total" in result.warnings


def test_r4_10_bad_value_row_goes_to_unrecognized() -> None:
    rows = [*ROWS, ("04/10/2026", "VALOR RUIM", "abc", ""), ("99/99/2026", "DATA RUIM", "1,00", "")]
    result = parse_csv(profile(), open_invoice_csv(rows), "f-2026-10.csv")
    assert len(result.lines) == 3
    assert len(result.unrecognized) == 2
    assert "VALOR RUIM" in result.unrecognized[0]


def test_r4_10_short_row_goes_to_unrecognized_and_blank_rows_are_skipped() -> None:
    data = "Data;Lançamento;Valor;Parcela\n01/10/2026;LOJA A;100,00;\n;;;\n02/10/2026;CURTA\n"
    result = parse_csv(profile(), data.encode(), "f-2026-10.csv")
    assert len(result.lines) == 1
    assert result.unrecognized == ["02/10/2026;CURTA"]


def test_r4_10_invalid_encoding_is_parse_error() -> None:
    data = "Data;Lançamento;Valor\n01/10/2026;CAFÉ;10,00\n".encode("latin-1")
    with pytest.raises(ParseError, match="decode"):
        parse_csv(profile(), data, "f-2026-10.csv")


def test_r4_10_latin1_profile_reads_latin1_file() -> None:
    data = "Data;Lançamento;Valor\n01/10/2026;CAFÉ;10,00\n".encode("latin-1")
    result = parse_csv(profile(csv={"encoding": "latin-1"}), data, "f-2026-10.csv")
    assert result.lines[0].description == "CAFÉ"


def test_csv_missing_mapped_column_is_parse_error() -> None:
    data = b"Data;Descricao;Valor\n01/10/2026;X;1,00\n"
    with pytest.raises(ParseError, match="Lançamento"):
        parse_csv(profile(), data, "f-2026-10.csv")


def test_csv_without_header_row_is_parse_error() -> None:
    with pytest.raises(ParseError, match="header"):
        parse_csv(profile(csv={"header_row": False}), open_invoice_csv(ROWS), "f.csv")
    with pytest.raises(ParseError, match="header"):
        parse_csv(profile(), b"", "f.csv")


def test_csv_skip_rows_and_comma_delimiter() -> None:
    data = b'Exportado em 18/10/2026\nData,Lan\xc3\xa7amento,Valor\n01/10/2026,LOJA,"1.234,56"\n'
    p = profile(csv={"delimiter": ",", "skip_rows": 1})
    result = parse_csv(p, data, "f-2026-10.csv")
    assert result.lines[0].amount == Decimal("1234.56")


def test_csv_ignore_classify_and_card_hint_column() -> None:
    p = profile(
        ignore=["^PAGAMENTO"],
        classify=[{"match": "IOF", "kind": "fee"}],
        csv={
            "columns": {
                "date": "Data",
                "desc": "Lançamento",
                "amount": "Valor",
                "card_hint": "Final",
            }
        },
    )
    data = (
        "Data;Lançamento;Valor;Final\n"
        "01/10/2026;LOJA;10,00;1111\n"
        "02/10/2026;IOF;1,00;\n"
        "03/10/2026;PAGAMENTO RECEBIDO;-500,00;\n"
    ).encode()
    result = parse_csv(p, data, "f-2026-10.csv")
    assert [ln.card_hint for ln in result.lines] == ["1111", None]
    assert [ln.kind for ln in result.lines] == ["expense", "fee"]
    assert result.ignored == ["03/10/2026;PAGAMENTO RECEBIDO;-500,00;"]


def test_csv_negative_means_expense_makes_amount_positive() -> None:
    result = parse_csv(profile(negative_means="expense"), open_invoice_csv(ROWS), "f-2026-10.csv")
    assert [ln.amount for ln in result.lines][-1] == Decimal("10.00")
    assert result.lines[-1].kind == "expense"


def test_csv_amount_format_us() -> None:
    p = profile(amount_format="us", csv={"delimiter": ","})
    data = b'Data,Lan\xc3\xa7amento,Valor\n01/10/2026,STORE,"1,234.56"\n'
    assert parse_csv(p, data, "f-2026-10.csv").lines[0].amount == Decimal("1234.56")


def test_csv_invoice_month_from_due_date_column() -> None:
    p = profile(
        invoice_month_from="due_date_column",
        filename_regex=None,
        csv={
            "columns": {
                "date": "Data",
                "desc": "Lançamento",
                "amount": "Valor",
                "due_date": "Vencimento",
            }
        },
    )
    data = (
        "Data;Lançamento;Valor;Vencimento\n"
        "01/10/2026;A;10,00;15/11/2026\n"
        "02/10/2026;B;10,00;xx\n"
        "03/10/2026;C;10,00;\n"
    ).encode()
    result = parse_csv(p, data, "sem-mes.csv")
    assert result.due_date == date(2026, 11, 15)
    assert result.invoice_month == "2026-11"


def test_csv_filename_without_month_leaves_invoice_month_empty() -> None:
    result = parse_csv(profile(), open_invoice_csv(ROWS), "fatura-aberta.csv")
    assert result.invoice_month is None


def test_csv_extrato_negative_is_income() -> None:
    p = profile(kind="extrato", open_invoice=False, invoice_month_from="ask", filename_regex=None)
    result = parse_csv(p, open_invoice_csv(ROWS), "extrato.csv")
    assert result.lines[-1].kind == "income"
    assert (result.period_from, result.period_to) == (date(2026, 10, 1), date(2026, 10, 3))
    assert "no_total" not in result.warnings


def test_csv_header_detection_helper() -> None:
    assert csv_header(open_invoice_csv(ROWS)) == ["Data", "Lançamento", "Valor", "Parcela"]
    assert csv_header("Data,Valor\n1,2\n".encode("latin-1")) == ["Data", "Valor"]
    assert csv_header("Data\tLançamento\n".encode("latin-1")) == ["Data", "Lançamento"]
    assert csv_header(b"so uma coluna\n") == []
    assert csv_header(b"\xff\xfe", encoding_candidates=("utf-8",)) == []
