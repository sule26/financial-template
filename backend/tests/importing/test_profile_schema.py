"""Profile schema contract (docs/06 "Formato", R4.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from expense_tracker.profiles import Profile, parse_profile
from fixtures.files import OPEN_INVOICE_CSV_PROFILE, STATEMENT_PROFILE

EXAMPLES = Path(__file__).resolve().parents[3] / "profiles" / "examples"

MINIMAL_PDF = {
    "id": "banco-x-fatura",
    "kind": "fatura",
    "detect": {"all": ["BANCO X"]},
    "transactions": {"line": r"^(?P<date>\d{2}/\d{2}) (?P<desc>.+) (?P<amount>[\d.]+,\d{2})$"},
}


def _yaml(**overrides: object) -> str:
    data = {**MINIMAL_PDF, **overrides}
    return yaml.safe_dump(data, allow_unicode=True)


def _tx(**overrides: object) -> dict:
    return {**MINIMAL_PDF["transactions"], **overrides}


def test_r4_1_minimal_pdf_profile_is_valid_with_documented_defaults() -> None:
    profile = parse_profile(_yaml())
    assert profile.id == "banco-x-fatura"
    assert profile.format == "pdf"
    assert profile.open_invoice is False
    tx = profile.transactions
    assert tx.sign == "auto"
    assert tx.amount_format == "br"
    assert tx.negative_means == "refund"
    assert tx.multiline is False


@pytest.mark.parametrize("name", ["inter-fatura.yaml", "nubank-fatura.yaml"])
def test_r4_1_example_profiles_are_valid(name: str) -> None:
    profile = parse_profile((EXAMPLES / name).read_text(encoding="utf-8"))
    assert profile.kind == "fatura"


def test_r4_10_fixture_profiles_are_valid() -> None:
    statement = parse_profile(STATEMENT_PROFILE)
    assert statement.kind == "extrato"
    assert statement.transactions.sign == "minus_is_debit"
    csv = parse_profile(OPEN_INVOICE_CSV_PROFILE)
    assert csv.format == "csv"
    assert csv.open_invoice is True
    assert csv.csv is not None and csv.csv.delimiter == ";"


def test_r4_10_csv_top_level_aliases_override_transactions() -> None:
    profile = parse_profile(
        OPEN_INVOICE_CSV_PROFILE + "negative_means: expense\nignore: ['PAGAMENTO']\n"
    )
    assert profile.tx.date_format == "%d/%m/%Y"
    assert profile.tx.amount_format == "br"
    assert profile.tx.negative_means == "expense"
    assert profile.tx.ignore == ["PAGAMENTO"]


def test_tx_without_aliases_is_transactions() -> None:
    profile = parse_profile(_yaml())
    assert profile.tx is profile.transactions


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"transactions": _tx(line="^(?P<date>[0-9")}, "invalid regex"),
        ({"transactions": _tx(line=r"^(?P<desc>.+) (?P<amount>\d+)$")}, "'date'"),
        ({"transactions": _tx(line=r"^(?P<date>\d+) (?P<amount>\d+)$")}, "'desc'"),
        ({"transactions": _tx(line=r"^(?P<date>\d+) (?P<desc>.+)$")}, "'amount'"),
        ({"transactions": _tx(installment="(")}, "installment: invalid regex"),
        ({"transactions": _tx(card_section="(")}, "card_section: invalid regex"),
        ({"transactions": _tx(card_section=r"Cartão (\d{4})")}, "card_section regex must have"),
        ({"transactions": _tx(ignore=["["])}, "ignore: invalid regex"),
        ({"transactions": _tx(section={"start": "("})}, "section: invalid regex"),
        ({"transactions": _tx(section={"start": "A", "end": "["})}, "section: invalid regex"),
        ({"transactions": _tx(sign="weird")}, "sign"),
        ({"page_noise": ["("]}, "page_noise: invalid regex"),
        ({"classify": [{"match": "(", "kind": "fee"}]}, "classify.match: invalid regex"),
        ({"classify": [{"match": "X", "tag": "nope"}]}, "tag"),
        ({"header": {"total": {"regex": r"Total (\d+)"}}}, "named group 'v'"),
        ({"header": {"total": {"regex": "(?P<v>"}}}, "invalid regex"),
        ({"header": {"total": {}}}, "exactly one of regex or sum_of"),
        (
            {"header": {"total": {"regex": "(?P<v>1)", "sum_of": [{"regex": "(?P<v>1)"}]}}},
            "exactly one of regex or sum_of",
        ),
        ({"header": {"total": {"sum_of": [{"regex": "("}]}}}, "invalid regex"),
        ({"header": {"unknown_field": {"regex": "(?P<v>1)"}}}, "unknown_field"),
        ({"detect": {"all": []}}, "pdf profiles need detect.all"),
        ({"transactions": {}}, "pdf profiles need transactions.line"),
        ({"id": "Banco X"}, "id"),
        ({"kind": "boleto"}, "kind"),
        ({"invoice_month_from": "filename"}, "needs filename_regex"),
        ({"invoice_month_from": "filename", "filename_regex": "("}, "filename_regex: invalid"),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_r4_1_invalid_profiles_are_rejected_with_message(overrides: dict, message: str) -> None:
    with pytest.raises(ValueError) as exc:
        parse_profile(_yaml(**overrides))
    assert message in str(exc.value)


def test_r4_10_csv_profile_without_csv_section_is_rejected() -> None:
    text = yaml.safe_dump(
        {"id": "y", "kind": "fatura", "format": "csv", "detect": {"columns": ["Data"]}}
    )
    with pytest.raises(ValueError, match="csv profiles need a csv section"):
        parse_profile(text)


def test_r4_10_csv_profile_without_detect_columns_is_rejected() -> None:
    text = yaml.safe_dump(
        {
            "id": "y",
            "kind": "fatura",
            "format": "csv",
            "detect": {},
            "csv": {"columns": {"date": "Data", "desc": "D", "amount": "V"}},
        }
    )
    with pytest.raises(ValueError, match="csv profiles need detect.columns"):
        parse_profile(text)


def test_r4_10_csv_delimiter_must_be_one_char() -> None:
    bad = OPEN_INVOICE_CSV_PROFILE.replace("delimiter: ';'", "delimiter: ';;'")
    with pytest.raises(ValueError, match="delimiter"):
        parse_profile(bad)


def test_invalid_yaml_is_reported() -> None:
    with pytest.raises(ValueError, match="invalid YAML"):
        parse_profile("id: [unclosed\n")


def test_non_mapping_yaml_is_reported() -> None:
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        parse_profile("- a\n- b\n")


def test_profile_model_accepts_dict_directly() -> None:
    profile = Profile.model_validate(MINIMAL_PDF)
    assert profile.detect.none == []
