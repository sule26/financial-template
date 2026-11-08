"""Profile loading: YAML errors, duplicates and Python plugins (docs/06 "Plugin Python")."""

from __future__ import annotations

import textwrap
from pathlib import Path

from expense_tracker.importing import parse_file_inline
from expense_tracker.profiles import load_profiles
from fixtures.files import OPEN_INVOICE_CSV_PROFILE, STATEMENT_PROFILE, pdf_bytes, write

PLUGIN = """
from expense_tracker.importing.result import ParseResult, RawLine
import datetime as dt


class Parser:
    id = "banco-y-fatura"
    kind = "fatura"

    def detect(self, text: str) -> bool:
        return "BANCO Y PLUGIN" in text

    def parse(self, pages: list[str]) -> ParseResult:
        lines = [p for page in pages for p in page.splitlines() if p.startswith("ITEM ")]
        return ParseResult(
            kind="fatura",
            profile_id=self.id,
            lines=[
                RawLine(index=i, date=dt.date(2026, 10, 1), description=ln[5:], amount="1.00")
                for i, ln in enumerate(lines)
            ],
        )
"""


def _plugin(directory: Path, name: str, source: str) -> None:
    write(directory / "plugins" / name, textwrap.dedent(source).encode())


def test_missing_directory_gives_empty_set(tmp_path: Path) -> None:
    loaded = load_profiles(tmp_path / "nope")
    assert loaded.profiles == {} and loaded.plugins == {} and loaded.errors == {}


def test_r4_1_loads_yaml_and_yml_and_records_sources(settings) -> None:
    d = settings.profiles_dir
    (d / "extrato.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
    (d / "aberta.yml").write_text(OPEN_INVOICE_CSV_PROFILE, encoding="utf-8")
    loaded = load_profiles(d)
    assert set(loaded.profiles) == {"banco-teste-extrato", "banco-y-fatura-aberta-csv"}
    assert loaded.sources["banco-teste-extrato"] == "extrato.yaml"
    assert loaded.sources["banco-y-fatura-aberta-csv"] == "aberta.yml"
    assert loaded.errors == {}


def test_invalid_profiles_are_collected_not_raised(settings) -> None:
    d = settings.profiles_dir
    (d / "a-ok.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
    (d / "broken.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    (d / "invalid.yaml").write_text("id: x\nkind: fatura\ndetect: {}\n", encoding="utf-8")
    (d / "dir.yaml").mkdir()  # unreadable as a file -> OSError collected
    loaded = load_profiles(d)
    assert set(loaded.profiles) == {"banco-teste-extrato"}
    assert "invalid YAML" in loaded.errors["broken.yaml"]
    assert "detect.all" in loaded.errors["invalid.yaml"]
    assert "dir.yaml" in loaded.errors


def test_duplicated_id_is_an_error_and_first_file_wins(settings) -> None:
    d = settings.profiles_dir
    (d / "a.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
    (d / "b.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
    loaded = load_profiles(d)
    assert loaded.sources["banco-teste-extrato"] == "a.yaml"
    assert "duplicated profile id" in loaded.errors["b.yaml"]


def test_valid_plugin_is_loaded_and_used_by_parse(settings) -> None:
    d = settings.profiles_dir
    _plugin(d, "banco_y.py", PLUGIN)
    loaded = load_profiles(d)
    assert loaded.errors == {}
    assert set(loaded.plugins) == {"banco-y-fatura"}
    assert loaded.sources["banco-y-fatura"] == "plugins/banco_y.py"
    pdf = write(
        settings.inbox_dir / "faturas" / "y.pdf",
        pdf_bytes([["BANCO Y PLUGIN", "ITEM CAFE", "ITEM PAO"]]),
    )
    outcome = parse_file_inline(pdf, "fatura", loaded, [])
    assert outcome.status == "ok", outcome.error
    assert outcome.profile_id == "banco-y-fatura"
    assert [ln.description for ln in outcome.result.lines] == ["CAFE", "PAO"]
    # the plugin's kind is respected: not considered for statements
    assert parse_file_inline(pdf, "extrato", loaded, []).status == "unknown_profile"


def test_plugin_returning_a_dict_is_validated(settings) -> None:
    d = settings.profiles_dir
    _plugin(
        d,
        "dict_plugin.py",
        """
        class Parser:
            id = "banco-d"
            kind = "extrato"
            def detect(self, text):
                return "BANCO D" in text
            def parse(self, pages):
                return {"kind": "extrato", "profile_id": "banco-d"}
        """,
    )
    loaded = load_profiles(d)
    pdf = write(settings.inbox_dir / "extratos" / "d.pdf", pdf_bytes([["BANCO D"]]))
    outcome = parse_file_inline(pdf, "extrato", loaded, [])
    assert outcome.status == "ok"
    assert outcome.result.profile_id == "banco-d"


def test_plugin_raising_during_parse_is_an_error_outcome(settings) -> None:
    d = settings.profiles_dir
    _plugin(
        d,
        "boom.py",
        """
        class Parser:
            id = "banco-b"
            kind = "fatura"
            def detect(self, text):
                return True
            def parse(self, pages):
                raise RuntimeError("layout mudou")
        """,
    )
    loaded = load_profiles(d)
    pdf = write(settings.inbox_dir / "faturas" / "b.pdf", pdf_bytes([["QUALQUER"]]))
    outcome = parse_file_inline(pdf, "fatura", loaded, [])
    assert outcome.status == "error"
    assert "RuntimeError" in outcome.error and "layout mudou" in outcome.error


def test_bad_plugins_are_collected(settings) -> None:
    d = settings.profiles_dir
    (d / "extrato.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
    _plugin(d, "no_parser.py", "class Other:\n    pass\n")
    _plugin(d, "explodes.py", "raise RuntimeError('import failed')\n")
    _plugin(d, "syntax.py", "def (:\n")
    detect = "    def detect(self, t):\n        return False\n"
    parse = "    def parse(self, p):\n        return None\n"
    _plugin(d, "missing_attr.py", "class Parser:\n    id = 'm'\n    kind = 'fatura'\n" + detect)
    _plugin(d, "bad_kind.py", "class Parser:\n    id = 'k'\n    kind = 'boleto'\n" + detect + parse)
    _plugin(
        d,
        "dup.py",
        "class Parser:\n    id = 'banco-teste-extrato'\n    kind = 'extrato'\n" + detect + parse,
    )
    loaded = load_profiles(d)
    assert loaded.plugins == {}
    errors = loaded.errors
    assert "Parser" in errors["plugins/no_parser.py"]
    assert "RuntimeError: import failed" in errors["plugins/explodes.py"]
    assert "SyntaxError" in errors["plugins/syntax.py"]
    assert "'parse'" in errors["plugins/missing_attr.py"]
    assert "kind" in errors["plugins/bad_kind.py"]
    assert "duplicated profile id" in errors["plugins/dup.py"]
    assert set(loaded.profiles) == {"banco-teste-extrato"}


def test_two_plugins_with_same_id(settings) -> None:
    d = settings.profiles_dir
    _plugin(d, "a.py", PLUGIN)
    _plugin(d, "b.py", PLUGIN)
    loaded = load_profiles(d)
    assert loaded.sources["banco-y-fatura"] == "plugins/a.py"
    assert "duplicated profile id" in loaded.errors["plugins/b.py"]
