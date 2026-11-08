"""Applying a YAML profile to extracted PDF text (docs/06; R4.4, R4.6, R4.7, R4.9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
import yaml

from expense_tracker.importing import ParseError, parse_text
from expense_tracker.importing.parser import detect_csv, detect_pdf
from expense_tracker.profiles import Profile, parse_profile
from fixtures.files import OPEN_INVOICE_CSV_PROFILE, STATEMENT_PROFILE

LINE = r"^(?P<date>\d{2}/\d{2}) (?P<desc>.+?) (?P<sign>[-−])?(?P<amount>[\d.]+,\d{2})$"


def make(**overrides: object) -> Profile:
    """A generic invoice profile with closing date (dates without year)."""
    data: dict = {
        "id": "banco-x-fatura",
        "kind": "fatura",
        "detect": {"all": ["BANCO X"]},
        "header": {
            "closing_date": {"regex": r"Fechamento (?P<v>\d{2}/\d{2}/\d{4})"},
            "due_date": {"regex": r"Vencimento (?P<v>\d{2}/\d{2}/\d{4})"},
            "total": {"regex": r"Total de lançamentos R\$ (?P<v>[\d.]+,\d{2})"},
            "amount_due": {"regex": r"Total a pagar R\$ (?P<v>-?[\d.]+,\d{2})"},
            "card_hint": {"regex": r"final (?P<v>\d{4})"},
        },
        "transactions": {
            "section": {"start": "^Lançamentos$", "end": "^Fim$"},
            "line": LINE,
            "date_format": "%d/%m",
            "installment": r"(?P<n>\d{1,2})/(?P<of>\d{1,2})$",
            "ignore": ["SALDO ANTERIOR", "PAGAMENTO RECEBIDO"],
        },
    }
    for key, value in overrides.items():
        if key == "transactions" or key == "header":
            data[key] = {**data[key], **value}  # type: ignore[dict-item]
        else:
            data[key] = value
    return parse_profile(yaml.safe_dump(data, allow_unicode=True))


def page(*body: str, closing: str = "03/01/2027", total: str = "150,00",
         due: str = "10/01/2027", amount_due: str = "150,00") -> list[str]:  # fmt: skip
    head = [
        "BANCO X fatura final 4321",
        f"Fechamento {closing}",
        f"Vencimento {due}",
        f"Total de lançamentos R$ {total}",
        f"Total a pagar R$ {amount_due}",
        "Lançamentos",
    ]
    return ["\n".join([*head, *body, "Fim", "01/01 LIXO 9,99"])]


# ------------------------------------------------------------------ header / sum


def test_r4_4_header_and_matching_sum_has_no_warning() -> None:
    result = parse_text(make(), page("20/12 LOJA A 100,00", "28/12 LOJA B 50,00"))
    assert result.closing_date == date(2027, 1, 3)
    assert result.due_date == date(2027, 1, 10)
    assert result.total == Decimal("150.00")
    assert result.amount_due == Decimal("150.00")
    assert result.card_hint == "4321"
    assert result.invoice_month == "2027-01"
    assert result.unrecognized == []
    assert [ln.amount for ln in result.lines] == [Decimal("100.00"), Decimal("50.00")]
    assert [ln.index for ln in result.lines] == [0, 1]
    assert result.warnings == []


def test_r4_4_sum_mismatch_reports_difference() -> None:
    result = parse_text(make(), page("20/12 LOJA A 100,00", total="110,00"))
    mismatch = [w for w in result.warnings if w.startswith("sum_mismatch")]
    assert len(mismatch) == 1
    assert "10.00" in mismatch[0]


def test_r4_4_one_cent_tolerance() -> None:
    ok = parse_text(make(), page("20/12 LOJA A 100,00", total="100,01"))
    assert not any(w.startswith("sum_mismatch") for w in ok.warnings)
    bad = parse_text(make(), page("20/12 LOJA A 100,00", total="100,02"))
    assert any(w.startswith("sum_mismatch") for w in bad.warnings)


def test_r4_4_ignored_and_transfer_lines_do_not_count_refunds_and_fees_do() -> None:
    profile = make(
        classify=[{"match": "PAGTO", "kind": "transfer"}, {"match": "IOF", "kind": "fee"}]
    )
    result = parse_text(
        profile,
        page(
            "20/12 LOJA A 100,00",
            "21/12 ESTORNO LOJA -20,00",
            "22/12 IOF 5,00",
            "23/12 PAGTO DEBITO -500,00",
            "24/12 SALDO ANTERIOR 999,00",
            total="85,00",
        ),
    )
    kinds = [ln.kind for ln in result.lines]
    assert kinds == ["expense", "refund", "fee", "transfer"]
    assert result.ignored == ["24/12 SALDO ANTERIOR 999,00"]
    assert result.warnings == []


def test_r4_9_amount_due_zero_keeps_all_purchases_and_compares_with_total() -> None:
    result = parse_text(
        make(), page("20/12 LOJA A 100,00", "28/12 LOJA B 50,00", amount_due="0,00")
    )
    assert result.amount_due == Decimal("0.00")
    assert result.total == Decimal("150.00")
    assert len(result.lines) == 2
    assert result.warnings == []


def test_r4_9_only_amount_due_skips_check_with_no_total() -> None:
    profile = make(
        header={"total": {"regex": r"NAO EXISTE (?P<v>[\d.]+,\d{2})"}},
    )
    result = parse_text(profile, page("20/12 LOJA A 100,00", amount_due="7,00"))
    assert result.total is None
    assert "no_total" in result.warnings
    assert not any(w.startswith("sum_mismatch") for w in result.warnings)


def test_no_total_when_header_has_no_total_field() -> None:
    data = make().model_dump()
    data["header"]["total"] = None
    profile = Profile.model_validate(data)
    result = parse_text(profile, page("20/12 LOJA A 100,00"))
    assert "no_total" in result.warnings


def test_total_sum_of_adds_parts_and_optional_parts_may_be_missing() -> None:
    profile = make(
        header={
            "total": {
                "sum_of": [
                    {"regex": r"Total de lançamentos R\$ (?P<v>[\d.]+,\d{2})"},
                    {"regex": r"Outros R\$ (?P<v>[\d.]+,\d{2})", "optional": True},
                ]
            }
        }
    )
    pages = page("20/12 LOJA A 100,00", "21/12 TARIFA 50,00", total="100,00")
    with_part = [pages[0].replace("Lançamentos\n", "Outros R$ 50,00\nLançamentos\n", 1)]
    assert parse_text(profile, with_part).total == Decimal("150.00")
    assert parse_text(profile, pages).total == Decimal("100.00")


def test_total_sum_of_missing_required_part_is_no_total() -> None:
    profile = make(header={"total": {"sum_of": [{"regex": r"Nada (?P<v>[\d.]+,\d{2})"}]}})
    assert parse_text(profile, page("20/12 LOJA A 100,00")).total is None


def test_total_sum_of_all_optional_missing_is_no_total() -> None:
    profile = make(
        header={"total": {"sum_of": [{"regex": r"Nada (?P<v>[\d.]+,\d{2})", "optional": True}]}}
    )
    result = parse_text(profile, page("20/12 LOJA A 100,00"))
    assert result.total is None
    assert "no_total" in result.warnings


def test_optional_header_missing_is_a_warning() -> None:
    profile = make(header={"due_date": {"regex": r"Venc (?P<v>\d{2}/\d{2}/\d{4})"}})
    result = parse_text(profile, page("20/12 LOJA A 100,00"))
    assert result.due_date is None
    assert "header_missing:due_date" in result.warnings


def test_required_header_missing_is_parse_error() -> None:
    profile = make(
        header={"due_date": {"regex": r"Venc (?P<v>\d{2}/\d{2}/\d{4})", "optional": False}}
    )
    with pytest.raises(ParseError, match="due_date"):
        parse_text(profile, page("20/12 LOJA A 100,00"))


def test_header_date_unparseable_is_parse_error() -> None:
    with pytest.raises(ParseError, match="closing_date"):
        parse_text(make(), page("20/12 LOJA A 100,00", closing="31/02/2027"))


def test_header_date_without_year_is_parse_error() -> None:
    profile = make(
        header={"closing_date": {"regex": r"Fechamento (?P<v>\d{2}/\d{2})", "format": "%d/%m"}}
    )
    with pytest.raises(ParseError, match="without year"):
        parse_text(profile, page("20/12 LOJA A 100,00"))


# ------------------------------------------------------------------ dates


def test_year_turn_line_before_january_closing_is_previous_year() -> None:
    result = parse_text(make(), page("28/12 LOJA A 100,00", "02/01 LOJA B 50,00"))
    assert [ln.date for ln in result.lines] == [date(2026, 12, 28), date(2027, 1, 2)]


def test_29_february_line_in_leap_year() -> None:
    result = parse_text(make(), page("29/02 LOJA A 150,00", closing="05/03/2028", due="12/03/2028"))
    assert result.lines[0].date == date(2028, 2, 29)


def test_dates_without_year_need_reference_date() -> None:
    profile = make(header={"closing_date": None, "due_date": None})
    with pytest.raises(ParseError, match="without year"):
        parse_text(profile, page("20/12 LOJA A 100,00"))


def test_line_with_invalid_date_is_parse_error() -> None:
    with pytest.raises(ParseError, match="cannot parse date"):
        parse_text(make(), page("31/02 LOJA A 100,00"))


def test_invalid_amount_in_line_is_parse_error() -> None:
    profile = make(transactions={"line": r"^(?P<date>\d{2}/\d{2}) (?P<desc>.+?) (?P<amount>\S+)$"})
    with pytest.raises(ParseError, match="invalid amount"):
        parse_text(profile, page("20/12 LOJA A abc"))


# ------------------------------------------------------------------ lines


def test_r4_6_installment_from_description() -> None:
    result = parse_text(make(), page("20/12 LOJA PARCELADA 03/10 100,00", "21/12 SEM 50,00"))
    first, second = result.lines
    assert (first.installment_n, first.installment_of) == (3, 10)
    assert (second.installment_n, second.installment_of) == (None, None)


def test_r4_6_installment_from_own_groups() -> None:
    profile = make(
        transactions={
            "line": r"^(?P<date>\d{2}/\d{2}) (?P<desc>.+?) "
            r"(?P<n>\d+)de(?P<of>\d+) (?P<amount>[\d.]+,\d{2})$",
            "installment": None,
        }
    )
    result = parse_text(profile, page("20/12 LOJA 2de5 150,00"))
    assert (result.lines[0].installment_n, result.lines[0].installment_of) == (2, 5)


def test_r4_7_card_sections_assign_cards_and_lines_before_section_have_none() -> None:
    profile = make(transactions={"card_section": r"^Cartão final (?P<v>\d{4})$"})
    result = parse_text(
        profile,
        page(
            "19/12 ANTES DA SECAO 10,00",
            "Cartão final 1111",
            "20/12 LOJA A 70,00",
            "Cartão final 2222",
            "21/12 LOJA B 70,00",
        ),
    )
    assert [ln.card_hint for ln in result.lines] == [None, "1111", "2222"]
    assert result.unrecognized == []


def test_r4_7_card_hint_group_per_line() -> None:
    profile = make(
        transactions={
            "line": r"^(?P<date>\d{2}/\d{2}) (?:\[(?P<card_hint>\d{4})\] )?"
            r"(?P<desc>.+?) (?P<amount>[\d.]+,\d{2})$"
        }
    )
    result = parse_text(profile, page("20/12 [9999] LOJA A 100,00", "21/12 LOJA B 50,00"))
    assert [ln.card_hint for ln in result.lines] == ["9999", None]


def test_lines_outside_section_are_skipped_and_unknown_lines_inside_are_unrecognized() -> None:
    result = parse_text(make(), page("20/12 LOJA A 150,00", "texto estranho"))
    assert result.unrecognized == ["texto estranho"]
    assert all("LIXO" not in ln.description for ln in result.lines)


def test_without_section_every_line_is_considered() -> None:
    data = make().model_dump()
    data["transactions"]["section"] = None
    profile = Profile.model_validate(data)
    result = parse_text(profile, page("20/12 LOJA A 150,00"))
    assert any("LIXO" in ln.description for ln in result.lines)


def test_section_without_end_runs_to_end_of_text() -> None:
    profile = make(transactions={"section": {"start": "^Lançamentos$"}})
    result = parse_text(profile, page("20/12 LOJA A 150,00"))
    assert any("LIXO" in ln.description for ln in result.lines)


def test_page_noise_lines_are_removed_before_parse() -> None:
    profile = make(page_noise=[r"^Página \d+ de \d+$"])
    pages = page("20/12 LOJA A 100,00", "Página 1 de 2", "28/12 LOJA B 50,00")
    result = parse_text(profile, pages)
    assert result.unrecognized == []
    assert len(result.lines) == 2


def test_description_whitespace_is_normalized() -> None:
    result = parse_text(make(), page("20/12 LOJA    A 150,00"))
    assert result.lines[0].description == "LOJA A"
    assert result.lines[0].raw == "20/12 LOJA    A 150,00"


def test_multiline_joins_continuation_into_previous_description() -> None:
    profile = make(transactions={"multiline": True})
    result = parse_text(profile, page("20/12 LOJA A 150,00", "SAO PAULO BR", "9 nao junta"))
    assert result.lines[0].description == "LOJA A SAO PAULO BR"
    assert result.lines[0].raw == "20/12 LOJA A 150,00\nSAO PAULO BR"
    assert result.unrecognized == ["9 nao junta"]


def test_multiline_without_previous_line_is_unrecognized() -> None:
    profile = make(transactions={"multiline": True})
    result = parse_text(profile, page("CABECALHO SOLTO", "20/12 LOJA A 150,00"))
    assert result.unrecognized == ["CABECALHO SOLTO"]


def test_continuation_without_multiline_is_unrecognized() -> None:
    result = parse_text(make(), page("20/12 LOJA A 150,00", "SAO PAULO BR"))
    assert result.unrecognized == ["SAO PAULO BR"]


def test_amount_format_us() -> None:
    profile = make(
        transactions={
            "line": r"^(?P<date>\d{2}/\d{2}) (?P<desc>.+?) (?P<sign>-)?(?P<amount>[\d,]+\.\d{2})$",
            "amount_format": "us",
        },
        header={"total": {"regex": r"Total US (?P<v>[\d,]+\.\d{2})"}},
    )
    pages = [page("20/12 STORE 1,234.56", "21/12 REFUND -34.56")[0] + "\nTotal US 1,200.00"]
    result = parse_text(profile, pages)
    assert [ln.amount for ln in result.lines] == [Decimal("1234.56"), Decimal("-34.56")]
    assert result.total == Decimal("1200.00")
    assert result.warnings == []


# ------------------------------------------------------------------ sign / kind


def test_sign_auto_minus_and_unicode_minus_are_credit() -> None:
    result = parse_text(
        make(), page("20/12 LOJA A 200,00", "21/12 ESTORNO -30,00", "22/12 DESCONTO −20,00")
    )
    assert [ln.amount for ln in result.lines] == [
        Decimal("200.00"),
        Decimal("-30.00"),
        Decimal("-20.00"),
    ]
    assert [ln.kind for ln in result.lines] == ["expense", "refund", "refund"]


def test_sign_minus_is_credit_same_as_auto() -> None:
    profile = make(transactions={"sign": "minus_is_credit"})
    result = parse_text(profile, page("20/12 LOJA 200,00", "21/12 ESTORNO −50,00", total="150,00"))
    assert [ln.amount for ln in result.lines] == [Decimal("200.00"), Decimal("-50.00")]


def test_sign_plus_is_credit() -> None:
    profile = make(
        transactions={
            "line": r"^(?P<date>\d{2}/\d{2}) (?P<desc>.+?) (?P<sign>\+)?(?P<amount>[\d.]+,\d{2})$",
            "sign": "plus_is_credit",
        }
    )
    result = parse_text(profile, page("20/12 LOJA 200,00", "21/12 ESTORNO +50,00", total="150,00"))
    assert [ln.amount for ln in result.lines] == [Decimal("200.00"), Decimal("-50.00")]


def test_negative_means_expense_kind() -> None:
    profile = make(transactions={"negative_means": "expense"})
    result = parse_text(profile, page("20/12 LOJA A -10,00", total="0,00"))
    assert result.lines[0].kind == "expense"


def test_classify_first_matching_kind_wins_and_tag_and_method() -> None:
    profile = make(
        classify=[
            {"match": "ANTECIP", "tag": "anticipation"},
            {"match": "DESC.*ANTECIP", "tag": "anticipation_discount"},
            {"match": "TARIFA|IOF", "kind": "fee"},
            {"match": "IOF", "kind": "expense"},
            {"match": "PIX", "payment_method": "pix"},
        ]
    )
    result = parse_text(
        profile,
        page("20/12 ANTECIPADA LOJA 100,00", "21/12 iof compra 5,00", "22/12 PIX LOJA 45,00"),
    )
    a, iof, pix = result.lines
    assert a.tag == "anticipation"
    assert iof.kind == "fee"  # case-insensitive, first kind wins
    assert pix.payment_method == "pix"


# ------------------------------------------------------------------ statement


def test_statement_minus_is_debit_period_account_and_classify() -> None:
    profile = parse_profile(STATEMENT_PROFILE)
    text = "\n".join(
        [
            "BANCO TESTE",
            "Extrato de conta",
            "Conta 12345-6",
            "Periodo 01/09/2026 a 30/09/2026",
            "Movimentacoes",
            "02/09/2026 PIX RECEBIDO FULANO 1.000,00",
            "05/09/2026 PIX ENVIADO MERCADO -80,00",
            "10/09/2026 PAGAMENTO FATURA CARTAO -500,00",
            "11/09/2026 APLICACAO CDB -200,00",
            "12/09/2026 RESGATE CDB 50,00",
            "13/09/2026 TARIFA PACOTE -9,90",
            "Saldo final 260,10",
        ]
    )
    result = parse_text(profile, [text])
    assert result.kind == "extrato"
    assert result.account_hint == "12345-6"
    assert (result.period_from, result.period_to) == (date(2026, 9, 1), date(2026, 9, 30))
    amounts = [ln.amount for ln in result.lines]
    assert amounts == [
        Decimal("-1000.00"),
        Decimal("80.00"),
        Decimal("500.00"),
        Decimal("200.00"),
        Decimal("-50.00"),
        Decimal("9.90"),
    ]
    kinds = [ln.kind for ln in result.lines]
    assert kinds == ["income", "expense", "transfer", "transfer", "transfer", "fee"]
    tags = [ln.tag for ln in result.lines]
    assert tags == [
        None,
        None,
        "invoice_payment",
        "investment_contribution",
        "investment_withdrawal",
        None,
    ]
    assert result.lines[1].payment_method == "pix"
    assert result.unrecognized == []
    assert "no_total" not in result.warnings  # sum check is for invoices only
    assert result.invoice_month is None


def test_statement_without_period_header_uses_line_dates() -> None:
    data = parse_profile(STATEMENT_PROFILE).model_dump()
    data["header"]["period_from"] = None
    data["header"]["period_to"] = None
    profile = Profile.model_validate(data)
    text = "BANCO TESTE\nMovimentacoes\n03/09/2026 A -1,00\n20/09/2026 B -2,00\nSaldo final 0,00"
    result = parse_text(profile, [text])
    assert (result.period_from, result.period_to) == (date(2026, 9, 3), date(2026, 9, 20))


def test_statement_without_lines_keeps_period_empty() -> None:
    data = parse_profile(STATEMENT_PROFILE).model_dump()
    data["header"]["period_from"] = None
    data["header"]["period_to"] = None
    profile = Profile.model_validate(data)
    result = parse_text(profile, ["Movimentacoes\nSaldo final 0,00"])
    assert result.lines == []
    assert result.period_from is None


# ------------------------------------------------------------------ detection helpers


def test_detect_pdf_all_and_none() -> None:
    profile = make(detect={"all": ["BANCO X", "Resumo"], "none": ["Extrato"]})
    assert detect_pdf(profile, "BANCO X ... Resumo")
    assert not detect_pdf(profile, "BANCO X apenas")
    assert not detect_pdf(profile, "BANCO X Resumo Extrato")


def test_detect_functions_respect_format() -> None:
    pdf = make()
    csv = parse_profile(OPEN_INVOICE_CSV_PROFILE)
    assert not detect_pdf(csv, "Data Lançamento Valor")
    assert not detect_csv(pdf, ["BANCO X"])
    assert detect_csv(csv, [" Data ", "Lançamento", "Valor", "Extra"])
    assert not detect_csv(csv, ["Data", "Valor"])
