"""Synthetic invoice/statement files for tests (no real personal data, docs/11).

The layouts imitate the line formats handled by ``profiles/examples`` (Inter-like and
Nubank-like) and a generic statement, so the example profiles can be tested end to end.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def pdf_bytes(pages: Sequence[Sequence[str]], password: str | None = None) -> bytes:
    """Render text lines into a PDF (one list of lines per page)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    # Vera ships with reportlab and has the glyphs real invoices use ("•", "−", accents)
    if "Vera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf"))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            c.setFont("Vera", 9)
            c.drawString(40, y, line)
            y -= 14
        c.showPage()
    c.save()
    data = buf.getvalue()
    if password is None:
        return data
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def br(value: str) -> str:
    """'1234.56' -> '1.234,56'."""
    whole, _, cents = f"{float(value):.2f}".partition(".")  # test-only formatting helper
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return ".".join(groups) + "," + cents


@dataclass
class Line:
    day: int
    month: int
    year: int
    description: str
    amount: str  # positive = purchase; negative = credit/payment
    card: str = "5678"


def inter_invoice(
    lines: Sequence[Line],
    due: str = "15/10/2026",
    holder: str = "FULANO DE TAL",
    main_card: str = "1234",
    total: str | None = None,
    amount_due: str = "0,00",
) -> bytes:
    """Inter-like invoice: sections per card, '- R$' purchases and '+ R$' payments."""
    purchases = sum(float(ln.amount) for ln in lines if float(ln.amount) > 0)
    total_txt = total if total is not None else br(f"{purchases:.2f}")
    header = [f"{holder}", f"0000****{main_card} {due} R$ {amount_due}"]
    page1 = [
        "Resumo da fatura",
        "Total da sua fatura",
        "Data de Vencimento",
        f"Este e o valor {due}",
        "www.bancointer.com.br",
    ]
    page2 = [
        *header,
        "Descritivo detalhado",
        f"Despesas do mês R$ {total_txt}",
        f"Fatura atual R$ {amount_due}",
    ]
    body = [*header, "Despesas da fatura"]
    by_card: dict[str, list[Line]] = {}
    for ln in lines:
        by_card.setdefault(ln.card, []).append(ln)
    for card, items in by_card.items():
        body.append(f"CARTÃO 0000****{card}")
        body.append("Data Movimentação Beneficiário Valor")
        for ln in items:
            sign = "+ " if float(ln.amount) < 0 else ""
            body.append(
                f"{ln.day:02d} de {PT[ln.month - 1]}. {ln.year} {ln.description} - "
                f"{sign}R$ {br(str(abs(float(ln.amount))))}"
            )
        body.append(f"Total CARTÃO 0000****{card} R$ 0,00")
    page_end = [*header, "Próxima fatura", "AMAZON (Parcela 10 de 12) R$ 336,83"]
    return pdf_bytes([page1, page2, body, page_end])


def nubank_invoice(
    lines: Sequence[Line],
    due: str = "19 OUT 2026",
    issued: str = "10 OUT 2026",
    payments: Sequence[tuple[str, str]] = (),
    amount_due: str = "0,00",
) -> bytes:
    """Nubank-like invoice: final per line ('•••• 1111'), '−R$' (U+2212) for credits."""
    purchases = sum(float(ln.amount) for ln in lines if float(ln.amount) > 0)
    credits = sum(-float(ln.amount) for ln in lines if float(ln.amount) < 0)
    page1 = ["Ola.", "Esta e a sua fatura", f"Data de vencimento: {due}", "Nubank"]
    page2 = [
        f"FATURA {due} EMISSÃO E ENVIO {issued}",
        "RESUMO DA FATURA ATUAL",
        "Total de compras de todos os cartões, 10 SET a 10 OUT R$ "
        + br(f"{purchases - credits:.2f}"),
        f"Total a pagar R$ {amount_due}",
    ]
    body = [
        f"FATURA {due} EMISSÃO E ENVIO {issued}",
        "TRANSAÇÕES DE 10 SET A 10 OUT",
        f"Fulano R$ {br(f'{purchases - credits:.2f}')}",
    ]
    for ln in lines:
        mon = PT[ln.month - 1].upper()
        hint = f"•••• {ln.card} " if ln.card else ""
        value = float(ln.amount)
        money = f"−R$ {br(str(-value))}" if value < 0 else f"R$ {br(str(value))}"
        body.append(f"{ln.day:02d} {mon} {hint}{ln.description} {money}")
    body.append("Pagamentos -R$ 0,00")
    for day, value in payments:
        body.append(f"{day} Pagamento em {day} −R$ {value}")
    return pdf_bytes([page1, page2, body])


STATEMENT_PROFILE = """\
id: banco-teste-extrato
kind: extrato
format: pdf
detect:
  all: ["BANCO TESTE", "Extrato de conta"]
header:
  account_hint: {regex: 'Conta (?P<v>[\\d-]+)'}
  period_from: {regex: 'Periodo (?P<v>\\d{2}/\\d{2}/\\d{4}) a', format: '%d/%m/%Y'}
  period_to: {regex: 'a (?P<v>\\d{2}/\\d{2}/\\d{4})$', format: '%d/%m/%Y'}
transactions:
  section: {start: 'Movimentacoes', end: 'Saldo final'}
  line: '^(?P<date>\\d{2}/\\d{2}/\\d{4}) (?P<desc>.+?) (?P<sign>-)?(?P<amount>[\\d.]+,\\d{2})$'
  date_format: '%d/%m/%Y'
  sign: minus_is_debit
classify:
  - {match: 'PAGAMENTO FATURA', kind: transfer, tag: invoice_payment}
  - {match: 'APLICACAO', kind: transfer, tag: investment_contribution}
  - {match: 'RESGATE', kind: transfer, tag: investment_withdrawal}
  - {match: 'PIX ENVIADO', payment_method: pix}
  - {match: 'TARIFA', kind: fee}
"""


def statement(
    rows: Sequence[tuple[str, str, str]],
    account: str = "12345-6",
    period: tuple[str, str] = ("01/09/2026", "30/09/2026"),
) -> bytes:
    """Generic statement. ``rows`` = (dd/mm/yyyy, description, amount) with amount > 0 = money
    OUT (debit, printed with '-') and amount < 0 = money IN (credit)."""
    lines = [
        "BANCO TESTE",
        "Extrato de conta",
        f"Conta {account}",
        f"Periodo {period[0]} a {period[1]}",
        "Movimentacoes",
    ]
    for day, desc, amount in rows:
        value = float(amount)
        text = br(str(abs(value)))
        lines.append(f"{day} {desc} {'-' if value > 0 else ''}{text}")
    lines.append("Saldo final 0,00")
    return pdf_bytes([lines])


OPEN_INVOICE_CSV_PROFILE = """\
id: banco-y-fatura-aberta-csv
kind: fatura
format: csv
open_invoice: true
csv:
  encoding: utf-8-sig
  delimiter: ';'
  columns: {date: 'Data', desc: 'Lançamento', amount: 'Valor', installment: 'Parcela'}
detect:
  columns: ['Data', 'Lançamento', 'Valor']
date_format: '%d/%m/%Y'
amount_format: br
invoice_month_from: filename
filename_regex: '(?P<y>\\d{4})-(?P<m>\\d{2})'
"""


def open_invoice_csv(rows: Sequence[tuple[str, str, str, str]]) -> bytes:
    """(dd/mm/yyyy, description, '1.234,56', 'n/of' or '')."""
    out = ["Data;Lançamento;Valor;Parcela"]
    out += [";".join(r) for r in rows]
    return ("\ufeff" + "\n".join(out) + "\n").encode("utf-8")


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
