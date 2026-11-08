"""Reading files: detection, passwords, CSV, timeout (docs/06, docs/13; R4.2, R4.5, R4.10)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from expense_tracker.importing import parse_file, parse_file_inline, reader
from expense_tracker.profiles import ProfileSet, load_profiles, parse_profile
from fixtures.files import (
    OPEN_INVOICE_CSV_PROFILE,
    STATEMENT_PROFILE,
    open_invoice_csv,
    pdf_bytes,
    statement,
    write,
)

ROWS = [("05/09/2026", "PIX ENVIADO MERCADO", "80.00"), ("06/09/2026", "PIX RECEBIDO", "-10.00")]


def _set(*texts: str) -> ProfileSet:
    loaded = ProfileSet()
    for text in texts:
        p = parse_profile(text)
        loaded.profiles[p.id] = p
    return loaded


def _clone(text: str, new_id: str) -> str:
    data = yaml.safe_load(text)
    data["id"] = new_id
    return yaml.safe_dump(data, allow_unicode=True)


def test_r4_2_exactly_one_profile_detected(tmp_path: Path) -> None:
    path = write(tmp_path / "extrato.pdf", statement(ROWS))
    outcome = parse_file_inline(path, "extrato", _set(STATEMENT_PROFILE), [])
    assert outcome.status == "ok"
    assert outcome.profile_id == "banco-teste-extrato"
    assert outcome.result.account_hint == "12345-6"
    assert outcome.result.period_to == date(2026, 9, 30)
    assert outcome.text and "BANCO TESTE" in outcome.text[0]
    assert outcome.result.lines[0].payment_method == "pix"


def test_r4_2_no_profile_is_unknown_profile_with_raw_text(tmp_path: Path) -> None:
    path = write(tmp_path / "x.pdf", pdf_bytes([["OUTRO BANCO", "nada"]]))
    outcome = parse_file_inline(path, "extrato", _set(STATEMENT_PROFILE), [])
    assert outcome.status == "unknown_profile"
    assert outcome.result is None
    assert "OUTRO BANCO" in outcome.text[0]


def test_r4_2_profile_of_other_kind_is_not_used(tmp_path: Path) -> None:
    path = write(tmp_path / "extrato.pdf", statement(ROWS))
    assert parse_file_inline(path, "fatura", _set(STATEMENT_PROFILE), []).status == (
        "unknown_profile"
    )


def test_r4_2_two_profiles_are_ambiguous(tmp_path: Path) -> None:
    path = write(tmp_path / "extrato.pdf", statement(ROWS))
    profiles = _set(STATEMENT_PROFILE, _clone(STATEMENT_PROFILE, "banco-teste-copia"))
    outcome = parse_file_inline(path, "extrato", profiles, [])
    assert outcome.status == "error"
    assert "ambiguous profiles" in outcome.error
    assert "banco-teste-copia" in outcome.error and "banco-teste-extrato" in outcome.error


def test_forced_profile_overrides_detection(tmp_path: Path) -> None:
    path = write(tmp_path / "extrato.pdf", statement(ROWS))
    profiles = _set(STATEMENT_PROFILE, _clone(STATEMENT_PROFILE, "banco-teste-copia"))
    outcome = parse_file_inline(path, "extrato", profiles, [], forced_profile="banco-teste-copia")
    assert outcome.status == "ok"
    assert outcome.profile_id == "banco-teste-copia"


def test_r4_5_password_protected_pdf(tmp_path: Path) -> None:
    path = write(tmp_path / "e.pdf", _encrypted_statement())
    profiles = _set(STATEMENT_PROFILE)
    ok = parse_file_inline(path, "extrato", profiles, ["errada", "s3nha"])
    assert ok.status == "ok", ok.error
    assert len(ok.result.lines) == 2


def _encrypted_statement() -> bytes:
    # same layout as fixtures.files.statement, encrypted with a user password
    lines = [
        "BANCO TESTE",
        "Extrato de conta",
        "Conta 12345-6",
        "Periodo 01/09/2026 a 30/09/2026",
        "Movimentacoes",
        "05/09/2026 PIX ENVIADO MERCADO -80,00",
        "06/09/2026 PIX RECEBIDO 10,00",
        "Saldo final 0,00",
    ]
    return pdf_bytes([lines], password="s3nha")


def test_r4_5_wrong_or_missing_password_is_error_mentioning_senha(tmp_path: Path) -> None:
    path = write(tmp_path / "e.pdf", _encrypted_statement())
    profiles = _set(STATEMENT_PROFILE)
    for passwords in ([], ["errada"]):
        outcome = parse_file_inline(path, "extrato", profiles, passwords)
        assert outcome.status == "error"
        assert "senha" in outcome.error
        assert "s3nha" not in outcome.error  # docs/06: password never leaks
        assert "errada" not in outcome.error


def test_corrupted_pdf_is_error(tmp_path: Path) -> None:
    path = write(tmp_path / "bad.pdf", b"%PDF-1.4\nnot really a pdf\n%%EOF")
    outcome = parse_file_inline(path, "extrato", _set(STATEMENT_PROFILE), [])
    assert outcome.status == "error"
    assert outcome.error


def test_parse_error_from_profile_becomes_error_outcome(tmp_path: Path) -> None:
    broken = STATEMENT_PROFILE.replace("date_format: '%d/%m/%Y'", "date_format: '%d/%m'")
    path = write(tmp_path / "extrato.pdf", statement(ROWS))
    outcome = parse_file_inline(path, "extrato", _set(broken), [])
    assert outcome.status == "error"
    assert "cannot parse date" in outcome.error


def test_r4_10_csv_detected_by_columns(tmp_path: Path) -> None:
    rows = [("01/10/2026", "LOJA", "10,00", "1/3")]
    path = write(tmp_path / "fatura-2026-10.csv", open_invoice_csv(rows))
    outcome = parse_file_inline(
        path, "fatura", _set(OPEN_INVOICE_CSV_PROFILE), [], as_of=date(2026, 10, 18)
    )
    assert outcome.status == "ok"
    assert outcome.result.open_invoice is True
    assert outcome.result.invoice_month == "2026-10"
    assert outcome.result.as_of == date(2026, 10, 18)
    assert (outcome.result.lines[0].installment_n, outcome.result.lines[0].installment_of) == (
        1,
        3,
    )


def test_r4_10_csv_unknown_ambiguous_and_forced(tmp_path: Path) -> None:
    path = write(tmp_path / "f-2026-10.csv", open_invoice_csv([("01/10/2026", "X", "1,00", "")]))
    assert parse_file_inline(path, "extrato", _set(OPEN_INVOICE_CSV_PROFILE), []).status == (
        "unknown_profile"
    )
    two = _set(OPEN_INVOICE_CSV_PROFILE, _clone(OPEN_INVOICE_CSV_PROFILE, "outro-csv"))
    ambiguous = parse_file_inline(path, "fatura", two, [])
    assert ambiguous.status == "error" and "ambiguous profiles" in ambiguous.error
    forced = parse_file_inline(path, "fatura", two, [], forced_profile="outro-csv")
    assert forced.status == "ok" and forced.profile_id == "outro-csv"


def test_r4_10_csv_with_wrong_encoding_is_error(tmp_path: Path) -> None:
    data = "Data;Lançamento;Valor\n01/10/2026;CAFÉ;10,00\n".encode("latin-1")
    path = write(tmp_path / "f-2026-10.csv", data)
    outcome = parse_file_inline(path, "fatura", _set(OPEN_INVOICE_CSV_PROFILE), [])
    assert outcome.status == "error"
    assert "decode" in outcome.error


def test_plugin_and_yaml_matching_same_file_are_ambiguous(settings) -> None:
    d = settings.profiles_dir
    (d / "extrato.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
    write(
        d / "plugins" / "p.py",
        b"class Parser:\n    id = 'plug'\n    kind = 'extrato'\n"
        b"    def detect(self, t):\n        return 'BANCO TESTE' in t\n"
        b"    def parse(self, p):\n        return None\n",
    )
    loaded = load_profiles(d)
    path = write(settings.inbox_dir / "extratos" / "e.pdf", statement(ROWS))
    outcome = parse_file_inline(path, "extrato", loaded, [])
    assert outcome.status == "error"
    assert "ambiguous profiles: banco-teste-extrato, plug" in outcome.error
    forced = parse_file_inline(path, "extrato", loaded, [], forced_profile="banco-teste-extrato")
    assert forced.status == "ok"


# ------------------------------------------------------------------ child process + timeout


def test_parse_file_in_child_process_returns_result(tmp_path: Path) -> None:
    path = write(tmp_path / "extrato.pdf", statement(ROWS))
    outcome = parse_file(path, "extrato", _set(STATEMENT_PROFILE), [], timeout=30)
    assert outcome.status == "ok", outcome.error
    assert outcome.profile_id == "banco-teste-extrato"
    assert len(outcome.result.lines) == 2


def test_parse_file_child_unknown_profile_has_no_result(tmp_path: Path) -> None:
    path = write(tmp_path / "x.pdf", pdf_bytes([["NADA"]]))
    outcome = parse_file(path, "extrato", _set(STATEMENT_PROFILE), [], timeout=30)
    assert outcome.status == "unknown_profile"
    assert outcome.result is None


CATASTROPHIC = """\
id: catastrofico
kind: extrato
detect:
  all: ["BANCO LENTO"]
transactions:
  line: '^(?P<desc>(a+)+)$(?P<date>)(?P<amount>)'
"""


def test_catastrophic_regex_times_out_as_error(tmp_path: Path) -> None:
    path = write(tmp_path / "lento.pdf", pdf_bytes([["BANCO LENTO", "a" * 30 + "!"]]))
    outcome = parse_file(path, "extrato", _set(CATASTROPHIC), [], timeout=1)
    assert outcome.status == "error"
    assert "timeout" in outcome.error


def test_child_process_dying_is_error(tmp_path: Path, settings) -> None:
    write(
        settings.profiles_dir / "plugins" / "die.py",
        b"import os\nclass Parser:\n    id = 'die'\n    kind = 'extrato'\n"
        b"    def detect(self, t):\n        return True\n"
        b"    def parse(self, p):\n        os._exit(3)\n",
    )
    loaded = load_profiles(settings.profiles_dir)
    path = write(tmp_path / "x.pdf", pdf_bytes([["X"]]))
    outcome = parse_file(path, "extrato", loaded, [], timeout=30)
    assert outcome.status == "error"
    assert "died" in outcome.error


def test_child_crash_is_reported_as_error(tmp_path: Path, monkeypatch) -> None:
    def explode(*args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(reader, "parse_file_inline", explode)
    path = write(tmp_path / "x.pdf", pdf_bytes([["X"]]))
    outcome = parse_file(path, "extrato", _set(STATEMENT_PROFILE), [], timeout=30)
    assert outcome.status == "error"
    assert "RuntimeError: kaboom" in outcome.error
