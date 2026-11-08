"""Investments: balance, contributions, yield, distribution (docs/15)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from expense_tracker.domain.allocation import parts, resolve_allocation
from expense_tracker.domain.models import Investment, SplitProfile, User
from expense_tracker.domain.money import ZERO
from expense_tracker.domain.months import month_of


@dataclass(frozen=True)
class Position:
    investment_id: str
    balance: Decimal
    balance_date: date | None
    net_contributions: Decimal
    yield_amount: Decimal | None
    stale: bool
    estimated: bool  # no snapshot: balance = net contributions


def net_contributions(inv: Investment, until: date | None = None) -> Decimal:
    total = ZERO
    for m in inv.movements:
        if until is not None and m.date > until:
            continue
        total += m.amount if m.type == "contribution" else -m.amount
    return total


def position(inv: Investment, today: date, stale_after_days: int = 45) -> Position:
    """Current balance = last snapshot; without snapshot, net contributions (estimated)."""
    snaps = sorted(inv.snapshots, key=lambda s: s.date)
    if not snaps:
        net = net_contributions(inv)
        return Position(inv.id, net, None, net, None, False, True)
    last = snaps[-1]
    net = net_contributions(inv, last.date)
    stale = (today - last.date).days > stale_after_days
    return Position(inv.id, last.balance, last.date, net, last.balance - net, stale, False)


def balance_at(inv: Investment, when: date) -> Decimal | None:
    """Last snapshot up to ``when``."""
    chosen: Decimal | None = None
    for s in sorted(inv.snapshots, key=lambda s: s.date):
        if s.date <= when:
            chosen = s.balance
    return chosen


@dataclass
class Portfolio:
    total: Decimal
    by_type: dict[str, Decimal]
    by_user: dict[str, Decimal]
    yield_total: Decimal
    positions: list[Position]


def portfolio(
    investments: Iterable[Investment],
    today: date,
    splits: Mapping[str, SplitProfile],
    users: Mapping[str, User],
) -> Portfolio:
    """R9.5: totals of open investments by type and by user."""
    by_type: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_user: dict[str, Decimal] = defaultdict(lambda: ZERO)
    total = ZERO
    ytotal = ZERO
    positions: list[Position] = []
    for inv in investments:
        if inv.closed_at is not None and inv.closed_at <= today:
            continue
        pos = position(inv, today)
        positions.append(pos)
        total += pos.balance
        ytotal += pos.yield_amount or ZERO
        by_type[inv.type] += pos.balance
        month = month_of(pos.balance_date or today)
        shares = resolve_allocation(inv.owners, month, splits, users).shares
        first = shares[0].user_id
        for uid, value in parts(pos.balance, shares, first).items():
            by_user[uid] += value
    return Portfolio(total, dict(by_type), dict(by_user), ytotal, positions)


def contributions_by_goal(investments: Iterable[Investment], month: str) -> dict[str, Decimal]:
    """R9.6: contributions of the month in investments linked to each goal."""
    out: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for inv in investments:
        if not inv.goal_id:
            continue
        for m in inv.movements:
            if month_of(m.date) == month and m.type == "contribution":
                out[inv.goal_id] += m.amount
    return dict(out)


def evolution(
    investments: Iterable[Investment], months: list[str]
) -> list[tuple[str, Decimal, Decimal]]:
    """(month, total balance at month end, cumulative net contributions)."""
    import calendar

    invs = list(investments)
    out: list[tuple[str, Decimal, Decimal]] = []
    for month in months:
        y, m = int(month[:4]), int(month[5:])
        end = date(y, m, calendar.monthrange(y, m)[1])
        bal = ZERO
        contrib = ZERO
        for inv in invs:
            if inv.closed_at is not None and inv.closed_at <= end:
                continue
            b = balance_at(inv, end)
            bal += b if b is not None else net_contributions(inv, end)
            contrib += net_contributions(inv, end)
        out.append((month, bal, contrib))
    return out
