"""Allocations: split profiles, owner/responsible inheritance, rules, precedence (docs/08)."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal

from expense_tracker.domain.models import (
    Account,
    Allocation,
    Benefit,
    Card,
    IncomeEntry,
    Rule,
    Share,
    SplitProfile,
    SplitRef,
    SplitVersion,
    User,
)
from expense_tracker.domain.money import CENT, HUNDRED, ZERO, allocate_amount
from expense_tracker.domain.normalize import normalize_description


class AllocationError(ValueError):
    """Allocation cannot be resolved (missing split, owners or responsible)."""


# ------------------------------------------------------------------- income


def _in_force(history: Sequence[IncomeEntry], month: str) -> Decimal:
    chosen = ZERO
    for entry in sorted(history, key=lambda e: e.from_month):
        if entry.from_month <= month:
            chosen = entry.amount
    return chosen


def income_for(
    user: User,
    month: str,
    benefit: bool = False,
    benefits: Sequence[Benefit] = (),
    one_off: bool = True,
) -> Decimal | None:
    """Income in force in ``month`` (greatest ``from_month <= month``); 0 or none -> ``None``.

    ``benefit=False``: salary (legacy ``income_history`` + every named income source, R14.4)
    + benefits credited in a checking account (e.g. home office aid) + one-off incomes of the
    month when ``one_off`` (the income-proportional split passes ``False``, R14.4).
    ``benefit=True``: benefits credited on a benefit card (e.g. VR) + legacy benefit history.
    """
    history = user.benefit_income_history if benefit else user.income_history
    total = _in_force(history, month)
    if not benefit:
        total += sum((_in_force(s.history, month) for s in user.incomes), ZERO)
        if one_off:
            total += sum((o.amount for o in user.one_off_incomes if o.month == month), ZERO)
    for b in benefits:
        if b.active and b.user_id == user.id and (b.destination == "card") == benefit:
            total += _in_force(b.amount_history, month)
    return None if total == ZERO else total


# ------------------------------------------------------------------- split profiles


@dataclass(frozen=True)
class ResolvedSplit:
    shares: tuple[Share, ...]
    warnings: tuple[str, ...] = ()


def _version_in_force(profile: SplitProfile, month: str) -> SplitVersion:
    """Version with the greatest ``from_month <= month``; before the first one, the first."""
    ordered = sorted(profile.history, key=lambda v: v.from_month)
    chosen = ordered[0]
    for version in ordered:
        if version.from_month <= month:
            chosen = version
    return chosen


def _equal_shares(members: Sequence[str]) -> tuple[Share, ...]:
    """Equal split among members; the cents residue goes to the first member."""
    base = (HUNDRED / len(members)).quantize(CENT, rounding=ROUND_DOWN)
    first = HUNDRED - base * (len(members) - 1)
    return tuple(Share(user_id=m, pct=first if i == 0 else base) for i, m in enumerate(members))


def _fallback(profile: SplitProfile, month: str, reason: str) -> ResolvedSplit:
    """R13.12 fallback when the proportional split cannot be computed.

    Most recent version with percentages and ``from_month <= month``; else the first version
    with percentages in the history; else an equal split among members. Always warns.
    """
    with_shares = sorted((v for v in profile.history if v.shares), key=lambda v: v.from_month)
    past = [v for v in with_shares if v.from_month <= month]
    if past:
        return ResolvedSplit(tuple(past[-1].shares), (f"proporção fixa usada: {reason}",))
    if with_shares:
        return ResolvedSplit(tuple(with_shares[0].shares), (f"proporção fixa usada: {reason}",))
    return ResolvedSplit(_equal_shares(profile.members), (f"divisão igual usada: {reason}",))


def resolve_split(
    profile: SplitProfile,
    month: str,
    users: Mapping[str, User],
    benefits: Sequence[Benefit] = (),
) -> ResolvedSplit:
    """Percentages of a split profile for a month (R6.11, R6.12, R13.12).

    The version in force in ``month`` decides the mode (its own ``mode`` or the profile default).
    """
    version = _version_in_force(profile, month)
    if profile.mode_of(version) == "fixed":
        return ResolvedSplit(tuple(version.shares))
    incomes: dict[str, Decimal] = {}
    missing: list[str] = []
    for member in profile.members:
        user = users.get(member)
        # R14.4: a one-off income (bonus) does not change the household split of its month.
        value = (
            income_for(user, month, benefits=benefits, one_off=False) if user is not None else None
        )
        if value is None:
            missing.append(member)
        else:
            incomes[member] = value
    if missing:
        names = ", ".join(users[m].name if m in users else m for m in missing)
        return _fallback(profile, month, f"renda de {names} ausente em {month}")
    total = sum(incomes.values(), ZERO)
    pcts = {
        m: (incomes[m] * HUNDRED / total).quantize(CENT, rounding=ROUND_HALF_EVEN)
        for m in profile.members
    }
    residue = HUNDRED - sum(pcts.values(), ZERO)
    if residue:
        top = max(profile.members, key=lambda m: (incomes[m], -profile.members.index(m)))
        pcts[top] += residue
    if any(p <= ZERO for p in pcts.values()):
        # A share rounding to 0.00 is not a valid allocation: fall back (R13.12).
        return _fallback(profile, month, f"renda muito desigual em {month}")
    return ResolvedSplit(tuple(Share(user_id=m, pct=pcts[m]) for m in profile.members))


def resolve_allocation(
    spec: Allocation,
    month: str,
    splits: Mapping[str, SplitProfile],
    users: Mapping[str, User],
    benefits: Sequence[Benefit] = (),
) -> ResolvedSplit:
    """Turn an ``AllocationSpec`` into concrete shares for ``month``."""
    if isinstance(spec, SplitRef):
        profile = splits.get(spec.split_id)
        if profile is None:
            raise AllocationError(f"unknown split profile {spec.split_id}")
        return resolve_split(profile, month, users, benefits)
    return ResolvedSplit(tuple(spec))


# ------------------------------------------------------------------- owners / responsible


@dataclass(frozen=True)
class Ownership:
    owners: Allocation
    responsible_user_id: str
    owners_origin: str  # "owners:card" | "owners:account"
    # R14.1: who pays the bank and how much; None = 100% responsible_user_id.
    responsibles: Allocation | None = None


def resolve_card(
    card: Card, cards: Mapping[str, Card], accounts: Mapping[str, Account]
) -> Ownership:
    """Inheritance additional card <- main card <- linked account (docs/08 resolve(card))."""
    chain: list[Card | Account] = [card]
    parent = cards.get(card.parent_card_id) if card.parent_card_id else None
    if card.parent_card_id and parent is None:
        raise AllocationError(f"card {card.id}: unknown parent card {card.parent_card_id}")
    if parent is not None:
        chain.append(parent)
    account_id = card.account_id or (parent.account_id if parent else None)
    if account_id:
        account = accounts.get(account_id)
        if account is None:
            raise AllocationError(f"card {card.id}: unknown account {account_id}")
        chain.append(account)
    owners: Allocation | None = None
    origin = "owners:account"
    for i, item in enumerate(chain):
        if item.owners is not None:
            owners = item.owners
            origin = "owners:card" if i == 0 else "owners:account"
            break
    # R14.1: the main responsible and the responsibles come together from the same level.
    payer = next((item for item in chain if item.responsible_user_id), None)
    if owners is None:
        raise AllocationError(f"card {card.id}: no owners (set owners or link an account)")
    if payer is None or payer.responsible_user_id is None:
        raise AllocationError(f"card {card.id}: no responsible user")
    return Ownership(owners, payer.responsible_user_id, origin, payer.responsibles)


def resolve_account(account: Account) -> Ownership:
    return Ownership(
        account.owners, account.responsible_user_id, "owners:account", account.responsibles
    )


def main_card_id(card: Card) -> str:
    """Id of the card that owns the invoice (additional cards bill on the main card)."""
    return card.parent_card_id or card.id


# ------------------------------------------------------------------- rules


@dataclass(frozen=True)
class RuleInput:
    description: str
    amount: Decimal
    card_id: str | None = None
    account_id: str | None = None


def _rule_matches(rule: Rule, item: RuleInput, category_id: str | None, use_category: bool) -> bool:
    w = rule.when
    if w.description_regex:
        try:
            if not re.search(w.description_regex, normalize_description(item.description), re.I):
                return False
        except re.error:
            return False
    if w.card_id is not None and w.card_id != item.card_id:
        return False
    if w.account_id is not None and w.account_id != item.account_id:
        return False
    if use_category and w.category_id is not None and w.category_id != category_id:
        return False
    if w.min_amount is not None and abs(item.amount) < w.min_amount:
        return False
    return not (w.max_amount is not None and abs(item.amount) > w.max_amount)


def _ordered(rules: Sequence[Rule]) -> list[Rule]:
    return sorted((r for r in rules if r.enabled), key=lambda r: (r.priority, r.id))


def rule_category(rules: Sequence[Rule], item: RuleInput) -> Rule | None:
    """Pass 1: lowest-priority enabled rule with ``then.category_id`` (ignores category cond.)."""
    for rule in _ordered(rules):
        if rule.then.category_id and _rule_matches(rule, item, None, use_category=False):
            return rule
    return None


def rule_allocation(rules: Sequence[Rule], item: RuleInput, category_id: str | None) -> Rule | None:
    """Pass 2: lowest-priority enabled rule with ``then.allocations``, category cond. applies."""
    for rule in _ordered(rules):
        if rule.then.allocations is not None and _rule_matches(
            rule, item, category_id, use_category=True
        ):
            return rule
    return None


# ------------------------------------------------------------------- precedence


@dataclass
class Defaults:
    """Result of applying the precedence (docs/08 "Precedência")."""

    allocations: Allocation
    allocation_origin: str
    category_id: str | None
    category_origin: str | None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LinkedDefaults:
    """Allocation/category of a linked plan, subscription or recurring purchase (level 2)."""

    origin: str  # "plan:<id>" | "subscription:<id>" | "recurring:<id>"
    allocations: Allocation | None
    category_id: str | None


def apply_precedence(
    item: RuleInput,
    ownership: Ownership,
    rules: Sequence[Rule],
    manual_allocations: Allocation | None = None,
    manual_category: str | None = None,
    linked: LinkedDefaults | None = None,
    last_category_for: Callable[[str], str | None] | None = None,
) -> Defaults:
    """Resolve default allocation and category for a transaction (R5.3, R1.11)."""
    # category: manual > linked > rule pass 1 > last used with same description > none
    category_id: str | None = None
    category_origin: str | None = None
    if manual_category:
        category_id, category_origin = manual_category, "manual"
    elif linked and linked.category_id:
        category_id, category_origin = linked.category_id, linked.origin
    else:
        rule = rule_category(rules, item)
        if rule is not None:
            category_id, category_origin = rule.then.category_id, f"rule:{rule.id}"
        elif last_category_for is not None:
            last = last_category_for(normalize_description(item.description))
            if last:
                category_id, category_origin = last, "history"

    if manual_allocations is not None:
        return Defaults(manual_allocations, "manual", category_id, category_origin)
    if linked and linked.allocations is not None:
        return Defaults(linked.allocations, linked.origin, category_id, category_origin)
    alloc_rule = rule_allocation(rules, item, category_id)
    if alloc_rule is not None and alloc_rule.then.allocations is not None:
        return Defaults(
            alloc_rule.then.allocations, f"rule:{alloc_rule.id}", category_id, category_origin
        )
    return Defaults(ownership.owners, ownership.owners_origin, category_id, category_origin)


# ------------------------------------------------------------------- parts


def remainder_index(shares: Sequence[Share], responsible_user_id: str) -> int:
    """Who absorbs the cents: responsible if present, else the largest pct (first on ties)."""
    for i, s in enumerate(shares):
        if s.user_id == responsible_user_id:
            return i
    best = 0
    for i, s in enumerate(shares):
        if s.pct > shares[best].pct:
            best = i
    return best


def parts(amount: Decimal, shares: Sequence[Share], responsible_user_id: str) -> dict[str, Decimal]:
    """Money part of each user (docs/08 "Arredondamento")."""
    values = allocate_amount(
        amount, [s.pct for s in shares], remainder_index(shares, responsible_user_id)
    )
    result: dict[str, Decimal] = {}
    for share, value in zip(shares, values, strict=True):
        result[share.user_id] = result.get(share.user_id, ZERO) + value
    return result


def equivalent(
    a: Allocation,
    b: Allocation,
    month: str,
    splits: Mapping[str, SplitProfile],
    users: Mapping[str, User],
) -> bool:
    """Two specs resolve to the same shares in ``month`` (used by R5.4)."""
    ra = {s.user_id: s.pct for s in resolve_allocation(a, month, splits, users).shares}
    rb = {s.user_id: s.pct for s in resolve_allocation(b, month, splits, users).shares}
    return ra == rb
