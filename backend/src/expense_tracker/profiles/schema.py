"""Bank profile schema (docs/06-perfis-de-banco.md "Formato")."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _compile(value: str, field: str) -> str:
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"{field}: invalid regex {value!r}: {exc}") from exc
    return value


class HeaderPart(Strict):
    regex: str
    optional: bool = False

    _r = field_validator("regex")(classmethod(lambda cls, v: _compile(v, "regex")))


class HeaderField(Strict):
    """A value read from the document header. ``v`` is the named group with the value."""

    regex: str | None = None
    format: str | None = None
    month_names: Literal["pt"] | None = None
    sum_of: list[HeaderPart] | None = None
    optional: bool = True

    @model_validator(mode="after")
    def _one(self) -> HeaderField:
        if (self.regex is None) == (self.sum_of is None):
            raise ValueError("header field needs exactly one of regex or sum_of")
        if self.regex is not None:
            _compile(self.regex, "regex")
            if "(?P<v>" not in self.regex:
                raise ValueError(f"header regex must have a named group 'v': {self.regex!r}")
        return self


class Header(Strict):
    due_date: HeaderField | None = None
    closing_date: HeaderField | None = None
    total: HeaderField | None = None
    amount_due: HeaderField | None = None
    card_hint: HeaderField | None = None
    account_hint: HeaderField | None = None
    period_from: HeaderField | None = None
    period_to: HeaderField | None = None
    as_of: HeaderField | None = None


class Section(Strict):
    start: str
    end: str | None = None

    _s = field_validator("start", "end")(classmethod(lambda cls, v: v and _compile(v, "section")))


class TransactionsSpec(Strict):
    section: Section | None = None
    card_section: str | None = None
    line: str | None = None
    date_format: str = "%d/%m/%Y"
    month_names: Literal["pt"] | None = None
    installment: str | None = None
    ignore: list[str] = Field(default_factory=list)
    negative_means: Literal["refund", "expense"] = "refund"
    sign: Literal["auto", "plus_is_credit", "minus_is_credit", "minus_is_debit"] = "auto"
    amount_format: Literal["br", "us"] = "br"
    multiline: bool = False

    @model_validator(mode="after")
    def _regexes(self) -> TransactionsSpec:
        for name in ("card_section", "line", "installment"):
            value = getattr(self, name)
            if value is not None:
                _compile(value, name)
        for pattern in self.ignore:
            _compile(pattern, "ignore")
        if self.line is not None:
            for group in ("date", "desc", "amount"):
                if f"(?P<{group}>" not in self.line:
                    raise ValueError(f"line regex must have the named group '{group}'")
        if self.card_section is not None and "(?P<v>" not in self.card_section:
            raise ValueError("card_section regex must have a named group 'v'")
        return self


Tag = Literal[
    "investment_contribution",
    "investment_withdrawal",
    "anticipation",
    "anticipation_discount",
    "invoice_payment",
]
KindName = Literal["expense", "refund", "fee", "income", "transfer", "settlement", "investment"]
MethodName = Literal["credit", "benefit", "debit", "pix", "transfer", "boleto", "cash"]


class ClassifyRule(Strict):
    match: str
    kind: KindName | None = None
    tag: Tag | None = None
    payment_method: MethodName | None = None

    _m = field_validator("match")(classmethod(lambda cls, v: _compile(v, "classify.match")))


class CsvColumns(Strict):
    date: str
    desc: str
    amount: str
    installment: str | None = None
    card_hint: str | None = None
    kind: str | None = None
    due_date: str | None = None


class CsvSpec(Strict):
    encoding: Literal["utf-8", "utf-8-sig", "latin-1", "cp1252"] = "utf-8"
    delimiter: str = Field(default=",", min_length=1, max_length=1)
    skip_rows: int = Field(default=0, ge=0)
    header_row: bool = True
    columns: CsvColumns


class Detect(Strict):
    all: list[str] = Field(default_factory=list)
    none: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


class Profile(Strict):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str | None = None
    kind: Literal["fatura", "extrato"]
    format: Literal["pdf", "csv"] = "pdf"
    open_invoice: bool = False
    detect: Detect
    password: str | None = None
    page_noise: list[str] = Field(default_factory=list)
    header: Header = Field(default_factory=Header)
    transactions: TransactionsSpec = Field(default_factory=TransactionsSpec)
    classify: list[ClassifyRule] = Field(default_factory=list)
    csv: CsvSpec | None = None
    invoice_month_from: Literal["due_date", "due_date_column", "filename", "ask"] = "due_date"
    filename_regex: str | None = None
    date_format: str | None = None  # CSV alias of transactions.date_format
    amount_format: Literal["br", "us"] | None = None  # CSV alias
    negative_means: Literal["refund", "expense"] | None = None  # CSV alias
    ignore: list[str] | None = None  # CSV alias

    @model_validator(mode="after")
    def _consistency(self) -> Profile:
        for pattern in self.page_noise:
            _compile(pattern, "page_noise")
        if self.format == "pdf":
            if not self.detect.all:
                raise ValueError("pdf profiles need detect.all")
            if self.transactions.line is None:
                raise ValueError("pdf profiles need transactions.line")
        else:
            if self.csv is None:
                raise ValueError("csv profiles need a csv section")
            if not self.detect.columns:
                raise ValueError("csv profiles need detect.columns")
        if self.invoice_month_from == "filename":
            if not self.filename_regex:
                raise ValueError("invoice_month_from: filename needs filename_regex")
            _compile(self.filename_regex, "filename_regex")
        return self

    # CSV top-level aliases override transactions.* (docs/06 CSV example)
    @property
    def tx(self) -> TransactionsSpec:
        update = {}
        for key in ("date_format", "amount_format", "negative_means", "ignore"):
            value = getattr(self, key)
            if value is not None:
                update[key] = value
        return self.transactions.model_copy(update=update) if update else self.transactions
