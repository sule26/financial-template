"""Example profiles (Inter, Nubank, Inter statement CSV) against synthetic files (docs/06)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from expense_tracker.importing import parse_file_inline
from expense_tracker.profiles import ProfileSet, load_profiles
from fixtures.files import Line, inter_invoice, nubank_invoice, write

EXAMPLES = Path(__file__).resolve().parents[3] / "profiles" / "examples"


@pytest.fixture(scope="module")
def examples() -> ProfileSet:
    loaded = load_profiles(EXAMPLES)
    assert loaded.errors == {}
    assert set(loaded.profiles) == {"inter-fatura", "nubank-fatura", "inter-extrato-csv"}
    return loaded


INTER_LINES = [
    Line(15, 9, 2026, "SUPERMERCADO ABC", "123.45", card="1234"),
    Line(16, 9, 2026, "AMAZON (Parcela 3 de 10)", "99.90", card="1234"),
    Line(20, 9, 2026, "PAGAMENTO ON LINE", "-500.00", card="1234"),
    Line(1, 10, 2026, "FARMACIA (Parcela 1 de 2)", "1250.00", card="5678"),
    Line(2, 10, 2026, "PADARIA", "8.50", card="5678"),
]


@pytest.fixture(scope="module")
def inter(tmp_path_factory: pytest.TempPathFactory, examples: ProfileSet):
    path = write(tmp_path_factory.mktemp("inter") / "inter.pdf", inter_invoice(INTER_LINES))
    outcome = parse_file_inline(path, "fatura", examples, [])
    assert outcome.status == "ok", outcome.error
    assert outcome.profile_id == "inter-fatura"
    return outcome.result


def test_r4_2_inter_detected_and_header(inter) -> None:
    assert inter.due_date == date(2026, 10, 15)
    assert inter.invoice_month == "2026-10"
    assert inter.card_hint == "1234"
    assert inter.total == Decimal("1481.85")


def test_r4_4_inter_zero_unrecognized_and_sum_matches_total(inter) -> None:
    assert inter.unrecognized == []
    assert len(inter.lines) == 5
    assert not any(w.startswith("sum_mismatch") for w in inter.warnings)
    assert "no_total" not in inter.warnings


def test_r4_9_inter_amount_due_zero_imports_all_purchases(inter) -> None:
    assert inter.amount_due == Decimal("0.00")
    purchases = [ln for ln in inter.lines if ln.kind == "expense"]
    assert sum(ln.amount for ln in purchases) == inter.total


def test_r4_6_inter_installments(inter) -> None:
    by_desc = {ln.description: ln for ln in inter.lines}
    assert (by_desc["AMAZON (Parcela 3 de 10)"].installment_n,
            by_desc["AMAZON (Parcela 3 de 10)"].installment_of) == (3, 10)  # fmt: skip
    assert by_desc["FARMACIA (Parcela 1 de 2)"].installment_of == 2
    assert by_desc["PADARIA"].installment_n is None


def test_r4_7_inter_card_sections(inter) -> None:
    assert [ln.card_hint for ln in inter.lines] == ["1234", "1234", "1234", "5678", "5678"]


def test_inter_payment_is_transfer_with_invoice_payment_tag(inter) -> None:
    payment = next(ln for ln in inter.lines if ln.description == "PAGAMENTO ON LINE")
    assert payment.amount == Decimal("-500.00")
    assert payment.kind == "transfer"
    assert payment.tag == "invoice_payment"


def test_inter_dates_with_pt_month_names(inter) -> None:
    assert inter.lines[0].date == date(2026, 9, 15)
    assert inter.lines[-1].date == date(2026, 10, 2)


def test_inter_next_invoice_section_is_never_imported(inter) -> None:
    assert all("Parcela 10 de 12" not in ln.description for ln in inter.lines)


def test_r4_4_inter_sum_mismatch_when_header_total_differs(tmp_path: Path, examples) -> None:
    path = write(tmp_path / "inter.pdf", inter_invoice(INTER_LINES, total="1.500,00"))
    outcome = parse_file_inline(path, "fatura", examples, [])
    assert outcome.status == "ok"
    assert any(w.startswith("sum_mismatch") for w in outcome.result.warnings)


NUBANK_LINES = [
    Line(12, 9, 2026, "Mercado Bom", "200.00", card="1111"),
    Line(15, 9, 2026, "Loja Parcela 2/6", "150.00", card="2222"),
    Line(20, 9, 2026, "Antecipada - Loja X - Parcela 6/10", "36.30", card=""),
    Line(20, 9, 2026, "Desconto Antecipação", "-3.63", card=""),
    Line(25, 9, 2026, "Estorno Mercado", "-20.00", card="1111"),
    Line(5, 10, 2026, "Padaria", "12.40", card="1111"),
]


@pytest.fixture(scope="module")
def nubank(tmp_path_factory: pytest.TempPathFactory, examples: ProfileSet):
    data = nubank_invoice(NUBANK_LINES, payments=[("05 OUT", "100,00")])
    path = write(tmp_path_factory.mktemp("nu") / "nubank.pdf", data)
    outcome = parse_file_inline(path, "fatura", examples, [])
    assert outcome.status == "ok", outcome.error
    assert outcome.profile_id == "nubank-fatura"
    return outcome.result


def test_r4_2_nubank_detected_and_header(nubank) -> None:
    assert nubank.due_date == date(2026, 10, 19)
    assert nubank.closing_date == date(2026, 10, 10)
    assert nubank.invoice_month == "2026-10"
    assert nubank.total == Decimal("375.07")
    assert nubank.amount_due == Decimal("0.00")


def test_r4_4_nubank_zero_unrecognized_and_sum_matches(nubank) -> None:
    assert nubank.unrecognized == []
    assert len(nubank.lines) == 6
    assert not any(w.startswith("sum_mismatch") for w in nubank.warnings)


def test_nubank_subtotal_line_is_ignored(nubank) -> None:
    assert any(raw.startswith("Fulano R$") for raw in nubank.ignored)


def test_r4_7_nubank_card_final_per_line(nubank) -> None:
    assert [ln.card_hint for ln in nubank.lines] == ["1111", "2222", None, None, "1111", "1111"]


def test_r4_6_nubank_installments(nubank) -> None:
    assert (nubank.lines[1].installment_n, nubank.lines[1].installment_of) == (2, 6)
    assert (nubank.lines[2].installment_n, nubank.lines[2].installment_of) == (6, 10)


def test_nubank_unicode_minus_is_credit(nubank) -> None:
    assert nubank.lines[3].amount == Decimal("-3.63")
    assert nubank.lines[4].amount == Decimal("-20.00")
    assert nubank.lines[4].kind == "refund"


def test_nubank_anticipation_tags(nubank) -> None:
    assert nubank.lines[2].tag == "anticipation"
    assert nubank.lines[3].tag == "anticipation_discount"
    assert nubank.lines[3].kind == "refund"


def test_nubank_year_inferred_from_closing_date(nubank) -> None:
    assert nubank.lines[0].date == date(2026, 9, 12)
    assert nubank.lines[-1].date == date(2026, 10, 5)


def test_nubank_payments_block_after_section_is_not_a_purchase(nubank) -> None:
    assert all(not ln.description.startswith("Pagamento em") for ln in nubank.lines)


def test_r4_9_nubank_amount_due_zero_with_purchases(tmp_path: Path, examples) -> None:
    data = nubank_invoice(NUBANK_LINES[:2], amount_due="0,00")
    outcome = parse_file_inline(write(tmp_path / "n.pdf", data), "fatura", examples, [])
    assert outcome.result.amount_due == Decimal("0.00")
    assert outcome.result.total == Decimal("350.00")
    assert len(outcome.result.lines) == 2


# docs/06#perfis-de-exemplo-validados-inter-e-nubank — Inter checking account CSV export
INTER_STATEMENT_CSV = (
    " Extrato Conta Corrente \n"
    "Conta ;000\n"
    "Período ;18/10/2026 a 18/11/2026\n"
    "Saldo ;100,00\n"
    "\n"
    "Data Lançamento;Histórico;Descrição;Valor;Saldo\n"
    "17/11/2026;Pix enviado ;Mercado X;-38,90;100,00\n"
    "16/11/2026;Pix recebido;Fulano;150,00;138,90\n"
    "15/11/2026;Pagamento efetuado;Pagamento Fatura - NOME;-1.355,92;-11,10\n"
    "14/11/2026;Aplicação;Cdb Porquinho;-5.000,00;1344,82\n"
    "13/11/2026;Resgate;Cdb Porquinho;798,37;6344,82\n"
    "12/11/2026;SAQUE BANCO 24H;SAQUE BANCO 24H;-360,00;5546,45\n"
    "11/11/2026;Pagamento de Título;PLANO DE SAUDE;-582,06;5906,45\n"
).encode()


def test_r14_38_inter_statement_csv_example(tmp_path: Path, examples: ProfileSet) -> None:
    path = write(tmp_path / "extrato.csv", INTER_STATEMENT_CSV)
    outcome = parse_file_inline(path, "extrato", examples, [])
    assert outcome.status == "ok", outcome.error
    assert outcome.profile_id == "inter-extrato-csv"
    result = outcome.result
    assert result is not None
    assert result.unrecognized == []
    assert [(ln.amount, ln.kind, ln.tag, ln.payment_method) for ln in result.lines] == [
        (Decimal("38.90"), "expense", None, "pix"),
        (Decimal("-150.00"), "income", None, "pix"),
        (Decimal("1355.92"), "transfer", "invoice_payment", None),
        (Decimal("5000.00"), "transfer", "investment_contribution", None),
        (Decimal("-798.37"), "transfer", "investment_withdrawal", None),
        (Decimal("360.00"), "transfer", None, "cash"),
        (Decimal("582.06"), "expense", None, "boleto"),
    ]
    assert result.lines[0].description == "Pix enviado - Mercado X"
    assert (result.period_from, result.period_to) == (date(2026, 11, 11), date(2026, 11, 17))
