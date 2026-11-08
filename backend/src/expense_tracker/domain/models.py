"""Domain models (docs/04-modelo-de-dados.md). Pure data; no I/O."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from expense_tracker.domain.money import HUNDRED, Money, Pct
from expense_tracker.domain.months import Month


class Model(BaseModel):
    """Base model: forbid unknown fields, validate on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ---------------------------------------------------------------- allocations


class Share(Model):
    user_id: str
    pct: Pct

    @field_validator("pct")
    @classmethod
    def _pct_range(cls, v: Decimal) -> Decimal:
        if v <= 0 or v > HUNDRED:
            raise ValueError("pct must be in (0, 100]")
        return v


class SplitRef(Model):
    split_id: str


def validate_shares(shares: list[Share]) -> list[Share]:
    """A fixed allocation: non-empty, unique users, sums to exactly 100.00 (docs/04 invariant 1)."""
    if not shares:
        raise ValueError("allocation must have at least one share")
    users = [s.user_id for s in shares]
    if len(set(users)) != len(users):
        raise ValueError("allocation has duplicated users")
    total = sum((s.pct for s in shares), Decimal("0"))
    if total != HUNDRED:
        raise ValueError(f"allocation must sum to 100.00, got {total:.2f}")
    return shares


FixedAllocation = Annotated[list[Share], Field(min_length=1)]
Allocation = FixedAllocation | SplitRef


def check_allocation(value: Allocation | None) -> Allocation | None:
    if isinstance(value, list):
        validate_shares(value)
    return value


def check_principal(principal: str, responsibles: Allocation | None) -> None:
    """R14.1: with a fixed list of responsibles, the main one must be in it."""
    if isinstance(responsibles, list) and principal not in {s.user_id for s in responsibles}:
        raise ValueError(f"responsible_user_id {principal!r} must be one of the responsibles")


# ---------------------------------------------------------------- enums


class Kind(StrEnum):
    EXPENSE = "expense"
    REFUND = "refund"
    FEE = "fee"
    INCOME = "income"
    TRANSFER = "transfer"
    SETTLEMENT = "settlement"
    INVESTMENT = "investment"


SPENDING_KINDS = frozenset({Kind.EXPENSE, Kind.REFUND, Kind.FEE})
INVOICE_TOTAL_KINDS = frozenset({Kind.EXPENSE, Kind.REFUND, Kind.FEE, Kind.INVESTMENT})


class PaymentMethod(StrEnum):
    CREDIT = "credit"
    BENEFIT = "benefit"
    DEBIT = "debit"
    PIX = "pix"
    TRANSFER = "transfer"
    BOLETO = "boleto"
    CASH = "cash"


ACCOUNT_METHODS: dict[str, frozenset[PaymentMethod]] = {
    "checking": frozenset(
        {PaymentMethod.DEBIT, PaymentMethod.PIX, PaymentMethod.TRANSFER, PaymentMethod.BOLETO}
    ),
    "benefit": frozenset({PaymentMethod.BENEFIT}),
    "cash": frozenset({PaymentMethod.CASH}),
}


# ---------------------------------------------------------------- people


class IncomeEntry(Model):
    from_month: Month
    amount: Money

    @field_validator("amount")
    @classmethod
    def _non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("income cannot be negative")
        return v


class IncomeSource(Model):
    """R14.4: one named income (e.g. a job) with its own history of amounts."""

    name: str = Field(min_length=1)
    history: list[IncomeEntry] = Field(default_factory=list)

    _check_history = field_validator("history")(classmethod(lambda cls, v: _unique_months(v)))


def _unique_months(history: list[IncomeEntry]) -> list[IncomeEntry]:
    months = [e.from_month for e in history]
    if len(set(months)) != len(months):
        raise ValueError("income history must have distinct from_month")
    return history


class OneOffIncome(Model):
    """R14.4: income received in a single month only (e.g. a bonus)."""

    month: Month
    amount: Money
    description: str = Field(default="Renda extra", min_length=1)

    @field_validator("amount")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("one-off income must be positive")
        return v


class User(Model):
    id: str
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    income_history: list[IncomeEntry] = Field(default_factory=list)
    benefit_income_history: list[IncomeEntry] = Field(default_factory=list)
    incomes: list[IncomeSource] = Field(default_factory=list)
    one_off_incomes: list[OneOffIncome] = Field(default_factory=list)
    # "Repassar para" (R13.11): everything this user owes is owed to this user instead.
    collector_user_id: str | None = None


class Benefit(Model):
    """A work benefit (R11.5): e.g. "VR" credited on a benefit card, or "Auxílio home office"
    credited in a checking account. Each benefit has its own name and monthly amount history."""

    id: str
    name: str = Field(min_length=1)
    user_id: str
    destination: Literal["card", "account"] = "card"
    account_id: str
    amount_history: list[IncomeEntry] = Field(default_factory=list)
    active: bool = True


SplitMode = Literal["fixed", "income_proportional"]


class SplitVersion(Model):
    """One version of a split profile (R6.11, R13.12).

    ``mode`` chooses how this version splits; ``None`` inherits ``SplitProfile.mode`` (legacy
    data). A fixed version needs ``shares`` summing 100.00; a proportional version may leave
    ``shares`` empty (when present they are only used as the fallback percentages).
    """

    from_month: Month
    mode: SplitMode | None = None
    shares: list[Share] = Field(default_factory=list)

    @field_validator("shares")
    @classmethod
    def _sum(cls, v: list[Share]) -> list[Share]:
        return validate_shares(v) if v else v

    @model_validator(mode="after")
    def _fixed_needs_shares(self) -> SplitVersion:
        if self.mode == "fixed" and not self.shares:
            raise ValueError("a fixed split version needs shares summing 100.00")
        return self


class SplitProfile(Model):
    id: str
    name: str = Field(min_length=1)
    members: list[str] = Field(min_length=1)
    # Default mode of versions without their own ``mode`` (legacy, R13.12).
    mode: SplitMode = "fixed"
    history: list[SplitVersion] = Field(min_length=1)

    def mode_of(self, version: SplitVersion) -> SplitMode:
        """Effective mode of a version: its own ``mode`` or the profile default."""
        return version.mode or self.mode

    @model_validator(mode="after")
    def _members_match(self) -> SplitProfile:
        if len(set(self.members)) != len(self.members):
            raise ValueError("split profile members must be unique")
        for version in self.history:
            if {s.user_id for s in version.shares} - set(self.members):
                raise ValueError("split version references a user that is not a member")
            if self.mode_of(version) == "fixed" and not version.shares:
                raise ValueError("a fixed split version needs shares summing 100.00")
        months = [v.from_month for v in self.history]
        if len(set(months)) != len(months):
            raise ValueError("split versions must have distinct from_month")
        return self


# ---------------------------------------------------------------- accounts and cards


class Account(Model):
    id: str
    name: str = Field(min_length=1)
    type: Literal["checking", "benefit", "cash"] = "checking"
    owners: Allocation
    responsible_user_id: str
    # R14.1: several people paying the bank, with percentages; None = only responsible_user_id.
    responsibles: Allocation | None = None
    profile_id: str | None = None
    account_hint: str | None = None
    confirm_manual_after_days: int | None = Field(default=None, ge=1)
    # R13.17: a benefit card (VR/VA) has no closing/due day, only the day its balance renews.
    renewal_day: int | None = Field(default=None, ge=1, le=31)

    _check_owners = field_validator("owners")(classmethod(lambda cls, v: check_allocation(v)))
    _check_responsibles = field_validator("responsibles")(
        classmethod(lambda cls, v: check_allocation(v))
    )

    @model_validator(mode="after")
    def _principal_in_responsibles(self) -> Account:
        check_principal(self.responsible_user_id, self.responsibles)
        return self

    @model_validator(mode="after")
    def _renewal_only_on_benefit(self) -> Account:
        if self.renewal_day is not None and self.type != "benefit":
            raise ValueError(
                "renewal_day is only allowed on benefit accounts (type 'benefit'), "
                f"got type '{self.type}'"
            )
        return self


class BillingEntry(Model):
    from_month: Month
    closing_day: int = Field(ge=1, le=31)
    due_day: int = Field(ge=1, le=31)


class Card(Model):
    id: str
    name: str = Field(min_length=1)
    parent_card_id: str | None = None
    account_id: str | None = None
    owners: Allocation | None = None
    responsible_user_id: str | None = None
    # R14.1: inherited together with responsible_user_id; needs it when set.
    responsibles: Allocation | None = None
    last_digits: list[Annotated[str, Field(pattern=r"^\d{4}$")]] = Field(default_factory=list)
    billing_history: list[BillingEntry] = Field(default_factory=list)
    limit: Money | None = None
    profile_id: str | None = None

    _check_owners = field_validator("owners")(classmethod(lambda cls, v: check_allocation(v)))

    _check_responsibles = field_validator("responsibles")(
        classmethod(lambda cls, v: check_allocation(v))
    )

    @model_validator(mode="after")
    def _principal(self) -> Card:
        if self.responsibles is not None and self.responsible_user_id is None:
            raise ValueError("responsibles needs responsible_user_id (the main responsible)")
        if self.responsible_user_id is not None:
            check_principal(self.responsible_user_id, self.responsibles)
        return self

    @model_validator(mode="after")
    def _billing(self) -> Card:
        if self.parent_card_id is None and not self.billing_history:
            raise ValueError("a main card needs billing_history (closing/due days)")
        return self


# ---------------------------------------------------------------- catalog


class Category(Model):
    id: str
    name: str = Field(min_length=1)
    color: str = "#868E96"
    budget: Money | None = None


class SavingsGoal(Model):
    id: str
    name: str = Field(min_length=1)
    monthly_amount: Money
    user_id: str | None = None


# ---------------------------------------------------------------- transactions


class Source(Model):
    type: Literal["import", "manual"]
    sha256: str | None = None
    path: str | None = None
    line: int | None = None


class InstallmentRef(Model):
    plan_id: str | None = None
    n: int = Field(ge=1)
    of: int = Field(ge=1)

    @model_validator(mode="after")
    def _n_le_of(self) -> InstallmentRef:
        if self.n > self.of:
            raise ValueError("installment n cannot exceed of")
        return self


class PaidInvoice(Model):
    card_id: str
    invoice_month: Month


class Links(Model):
    subscription_id: str | None = None
    recurring_purchase_id: str | None = None
    investment_id: str | None = None
    settlement_id: str | None = None
    paid_invoice: PaidInvoice | None = None
    internal_transfer_fingerprint: str | None = None
    anticipation_plan_id: str | None = None


class Suggestion(Model):
    type: str
    target_id: str | None = None
    score: Pct | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    candidates: list[str] = Field(default_factory=list)
    rejected: bool = False


class ReviewInfo(Model):
    status: Literal["pending", "needs_choice", "overlap"] = "pending"
    suggestions: list[Suggestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Transaction(Model):
    id: str
    fingerprint: str | None = None
    kind: Kind = Kind.EXPENSE
    source: Source
    provisional: bool = False
    payment_method: PaymentMethod = PaymentMethod.CREDIT
    card_id: str | None = None
    account_id: str | None = None
    purchase_date: dt.date
    invoice_month: Month
    description: str = Field(min_length=1)
    amount: Money
    category_id: str | None = None
    installment: InstallmentRef | None = None
    links: Links = Field(default_factory=Links)
    allocations: Allocation | None = None
    allocation_origin: str | None = None
    note: str | None = None
    income_type: Literal["cash", "benefit"] | None = None
    tag: str | None = None
    review: ReviewInfo | None = None
    created_at: dt.datetime | None = None

    _check_alloc = field_validator("allocations")(classmethod(lambda cls, v: check_allocation(v)))

    @model_validator(mode="after")
    def _owner(self) -> Transaction:
        if self.payment_method is PaymentMethod.CREDIT:
            if self.card_id is None:
                raise ValueError("credit transactions need card_id")
        elif self.account_id is None:
            raise ValueError("non-credit transactions need account_id")
        return self


# ---------------------------------------------------------------- plans, subscriptions, recurring


class Origin(Model):
    type: Literal["import", "manual"] = "manual"
    fingerprint: str | None = None


class Anticipation(Model):
    from_n: int = Field(ge=1)
    target_month: Month
    amount: Money | None = None
    linked_fingerprints: list[str] = Field(default_factory=list)


class StatusOverride(Model):
    status: Literal["cancelled", "anticipated_at_bank"] = "cancelled"
    from_n: int = Field(ge=1)


class InstallmentPlan(Model):
    id: str
    origin: Origin = Field(default_factory=Origin)
    card_id: str
    description: str = Field(min_length=1)
    total_installments: int = Field(ge=1, le=120)
    first_invoice_month: Month
    total_amount: Money
    installment_amount: Money | None = None
    category_id: str | None = None
    allocations: Allocation | None = None
    status_override: StatusOverride | None = None
    anticipation: Anticipation | None = None
    warnings: list[str] = Field(default_factory=list)

    _check_alloc = field_validator("allocations")(classmethod(lambda cls, v: check_allocation(v)))

    @model_validator(mode="after")
    def _ranges(self) -> InstallmentPlan:
        n = self.total_installments
        if self.anticipation and self.anticipation.from_n > n:
            raise ValueError("anticipation.from_n beyond total_installments")
        if self.status_override and self.status_override.from_n > n:
            raise ValueError("status_override.from_n beyond total_installments")
        return self


class PriceEntry(Model):
    """R14.9: price from a month on (subscriptions: invoice month; recurring: purchase month)."""

    from_month: Month
    amount: Money

    @field_validator("amount")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be positive")
        return v


def price_in(base: Decimal, history: list[PriceEntry], month: str) -> Decimal:
    """Price in force in ``month``: latest entry with ``from_month <= month``, else the base."""
    chosen = base
    for entry in sorted(history, key=lambda e: e.from_month):
        if entry.from_month <= month:
            chosen = entry.amount
    return chosen


class Pause(Model):
    """R14.11: months in which a subscription/recurring purchase was off (until None = still)."""

    from_month: Month
    until_month: Month | None = None

    @model_validator(mode="after")
    def _order(self) -> Pause:
        if self.until_month is not None and self.until_month < self.from_month:
            raise ValueError("pause until_month is before from_month")
        return self


def paused_in(pauses: list[Pause], month: str) -> bool:
    return any(
        p.from_month <= month and (p.until_month is None or month <= p.until_month) for p in pauses
    )


def _distinct_prices(history: list[PriceEntry]) -> list[PriceEntry]:
    months = [e.from_month for e in history]
    if len(set(months)) != len(months):
        raise ValueError("price history must have distinct from_month")
    return history


class Subscription(Model):
    id: str
    description: str = Field(min_length=1)
    amount: Money
    period: Literal["monthly", "annual"] = "monthly"
    month_of_year: int | None = Field(default=None, ge=1, le=12)
    payment_method: PaymentMethod = PaymentMethod.CREDIT
    card_id: str | None = None
    account_id: str | None = None
    start_month: Month
    end_month: Month | None = None
    category_id: str | None = None
    allocations: Allocation | None = None
    # R14.9: price changes (reajustes) from a month on; ``amount`` is the price before them.
    price_history: list[PriceEntry] = Field(default_factory=list)

    _check_prices = field_validator("price_history")(
        classmethod(lambda cls, v: _distinct_prices(v))
    )

    def amount_in(self, month: str) -> Decimal:
        return price_in(self.amount, self.price_history, month)

    # R14.11: periods when it was off; no charge is expected in those months.
    pauses: list[Pause] = Field(default_factory=list)

    def paused_in(self, month: str) -> bool:
        return paused_in(self.pauses, month)

    _check_alloc = field_validator("allocations")(classmethod(lambda cls, v: check_allocation(v)))

    @model_validator(mode="after")
    def _check(self) -> Subscription:
        if self.period == "annual" and self.month_of_year is None:
            raise ValueError("annual subscriptions need month_of_year")
        if self.end_month is not None and self.end_month < self.start_month:
            raise ValueError("end_month before start_month")
        if self.card_id is None and self.account_id is None:
            raise ValueError("subscription needs card_id or account_id")
        return self


class Interval(Model):
    value: int = Field(ge=1, le=3650)
    unit: Literal["days", "weeks", "months"] = "days"

    @property
    def days(self) -> int:
        """Approximate length in days (used for tolerances)."""
        return {"days": 1, "weeks": 7, "months": 30}[self.unit] * self.value


class RecurringPurchase(Model):
    id: str
    description: str = Field(min_length=1)
    match_description: str | None = None
    estimated_amount: Money
    every: Interval
    last_date: dt.date
    payment_method: PaymentMethod = PaymentMethod.CREDIT
    card_id: str | None = None
    account_id: str | None = None
    category_id: str | None = None
    allocations: Allocation | None = None
    active: bool = True
    skipped_dates: list[dt.date] = Field(default_factory=list)
    next_date: dt.date | None = None
    # R14.9: estimated price from a month on (month of the purchase date).
    price_history: list[PriceEntry] = Field(default_factory=list)

    _check_prices = field_validator("price_history")(
        classmethod(lambda cls, v: _distinct_prices(v))
    )

    def amount_in(self, month: str) -> Decimal:
        return price_in(self.estimated_amount, self.price_history, month)

    # R14.11: periods when it was off (month of the purchase date); none expected then.
    pauses: list[Pause] = Field(default_factory=list)

    def paused_in(self, month: str) -> bool:
        return paused_in(self.pauses, month)

    _check_alloc = field_validator("allocations")(classmethod(lambda cls, v: check_allocation(v)))

    @model_validator(mode="after")
    def _owner(self) -> RecurringPurchase:
        if self.card_id is None and self.account_id is None:
            raise ValueError("recurring purchase needs card_id or account_id")
        return self


# ---------------------------------------------------------------- rules, settlements, annotations


class RuleWhen(Model):
    description_regex: str | None = None
    card_id: str | None = None
    account_id: str | None = None
    category_id: str | None = None
    min_amount: Money | None = None
    max_amount: Money | None = None


class RuleThen(Model):
    category_id: str | None = None
    allocations: Allocation | None = None

    _check_alloc = field_validator("allocations")(classmethod(lambda cls, v: check_allocation(v)))


class Rule(Model):
    id: str
    priority: int = 100
    enabled: bool = True
    when: RuleWhen = Field(default_factory=RuleWhen)
    then: RuleThen = Field(default_factory=RuleThen)


class Settlement(Model):
    id: str
    origin: Origin = Field(default_factory=Origin)
    from_user_id: str
    to_user_id: str
    amount: Money
    date: dt.date
    month: Month
    note: str | None = None
    warnings: list[str] = Field(default_factory=list)
    # R13.16: optional link to one receivable (main card or account + invoice month)
    card_id: str | None = None
    account_id: str | None = None
    invoice_month: Month | None = None

    @model_validator(mode="after")
    def _distinct(self) -> Settlement:
        if self.from_user_id == self.to_user_id:
            raise ValueError("settlement from and to must differ")
        if self.amount <= 0:
            raise ValueError("settlement amount must be positive")
        if self.card_id is not None and self.account_id is not None:
            raise ValueError("settlement links to a card or an account, not both")
        if (self.card_id or self.account_id) and self.invoice_month is None:
            raise ValueError("a settlement linked to a card/account needs invoice_month")
        return self

    @property
    def linked(self) -> bool:
        """True when the settlement pays one receivable (R13.16), not just the net balance."""
        return self.invoice_month is not None


class Annotation(Model):
    fingerprint: str
    category_id: str | None = None
    allocations: Allocation | None = None
    note: str | None = None
    kind: Kind | None = None
    link_choices: dict[str, str] = Field(default_factory=dict)
    source_files: list[str] = Field(default_factory=list)
    description: str | None = None
    purchase_date: dt.date | None = None
    amount: Money | None = None
    owner_id: str | None = None
    updated_at: dt.datetime | None = None

    _check_alloc = field_validator("allocations")(classmethod(lambda cls, v: check_allocation(v)))


# ---------------------------------------------------------------- investments


class Snapshot(Model):
    date: dt.date
    balance: Money


class Movement(Model):
    date: dt.date
    type: Literal["contribution", "withdrawal"]
    amount: Money
    origin: Origin = Field(default_factory=Origin)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("amount")
    @classmethod
    def _positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("movement amount must be positive")
        return v


InvestmentType = Literal[
    "emergency_reserve", "fixed_income", "stocks", "funds", "pension", "crypto", "other"
]


InstitutionType = Literal["broker", "exchange", "pension", "bank", "other"]


class Institution(Model):
    """R13.15: where an investment lives when it is not one of the registered accounts."""

    id: str
    name: str = Field(min_length=1)
    type: InstitutionType = "other"


class Investment(Model):
    id: str
    name: str = Field(min_length=1)
    institution: str | None = None  # legacy free text, still accepted
    institution_id: str | None = None  # R13.15: an account id or an institution id
    type: InvestmentType = "other"
    owners: Allocation
    goal_id: str | None = None
    account_id: str | None = None
    snapshots: list[Snapshot] = Field(default_factory=list)
    movements: list[Movement] = Field(default_factory=list)
    closed_at: dt.date | None = None

    _check_owners = field_validator("owners")(classmethod(lambda cls, v: check_allocation(v)))
