"""Investments: position, yield, portfolio, goals, evolution (docs/15)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from builders import ANA, EU, Builders

from expense_tracker.domain.investments import (
    balance_at,
    contributions_by_goal,
    evolution,
    net_contributions,
    portfolio,
    position,
)

D = Decimal
mk = Builders

MOVES = [
    (date(2026, 9, 1), "contribution", 20000),
    (date(2026, 10, 5), "contribution", 500),
]
SNAPS = [(date(2026, 9, 30), 20150), (date(2026, 10, 31), 20890)]


def test_r9_5_yield_example_table() -> None:
    # docs/15#regras (example table): yield 150 at 2026-09-30, 390 at 2026-10-31
    first = mk.investment(snapshots=SNAPS[:1], movements=MOVES)
    pos = position(first, date(2026, 10, 12))
    assert (pos.balance, pos.net_contributions, pos.yield_amount) == (
        D("20150.00"), D("20000.00"), D("150.00"),
    )  # fmt: skip
    assert pos.balance_date == date(2026, 9, 30) and not pos.estimated

    full = mk.investment(snapshots=SNAPS, movements=MOVES)
    pos = position(full, date(2026, 11, 1))
    assert (pos.balance, pos.net_contributions, pos.yield_amount) == (
        D("20890.00"), D("20500.00"), D("390.00"),
    )  # fmt: skip
    assert net_contributions(full, date(2026, 10, 4)) == D("20000.00")
    assert net_contributions(full) == D("20500.00")


def test_r9_5_withdrawal_reduces_net_contributions() -> None:
    inv = mk.investment(movements=[*MOVES, (date(2026, 10, 20), "withdrawal", 1500)])
    assert net_contributions(inv) == D("19000.00")


def test_r9_5_without_snapshot_balance_is_net_contributions_estimated() -> None:
    # docs/15: no snapshot -> net contributions with warning "saldo não informado"
    pos = position(mk.investment(movements=MOVES), date(2026, 10, 12))
    assert pos.balance == D("20500.00")
    assert pos.estimated and pos.yield_amount is None and pos.balance_date is None
    assert not pos.stale


def test_r9_5_stale_snapshot_after_45_days() -> None:
    inv = mk.investment(snapshots=SNAPS[:1], movements=MOVES)
    assert not position(inv, date(2026, 11, 14)).stale  # 45 days
    assert position(inv, date(2026, 11, 15)).stale  # 46 days


def test_r9_2_balance_at_past_date_is_last_snapshot_until_then() -> None:
    inv = mk.investment(snapshots=list(reversed(SNAPS)), movements=MOVES)
    assert balance_at(inv, date(2026, 9, 29)) is None
    assert balance_at(inv, date(2026, 10, 15)) == D("20150.00")
    assert balance_at(inv, date(2026, 12, 1)) == D("20890.00")


def test_r9_5_portfolio_totals_by_type_and_user_with_split_versions() -> None:
    # share per user resolved by the snapshot month (split version changes in 2026-10)
    casal = mk.split("split_casal", [("2026-01", [(EU, 60), (ANA, 40)]),
                                     ("2026-10", [(EU, 50), (ANA, 50)])])  # fmt: skip
    splits = {casal.id: casal}
    reserva = mk.investment(
        "inv_reserva", owners=mk.ref("split_casal"), snapshots=SNAPS[:1], movements=MOVES
    )
    acoes = mk.investment("inv_acoes", type="stocks", snapshots=[(date(2026, 10, 10), 1000)],
                          movements=[(date(2026, 10, 1), "contribution", 1100)])  # fmt: skip
    result = portfolio([reserva, acoes], date(2026, 10, 12), splits, {})
    assert result.total == D("21150.00")
    assert result.by_type == {"emergency_reserve": D("20150.00"), "stocks": D("1000.00")}
    # reserva snapshot is in 2026-09 -> 60/40
    assert result.by_user == {EU: D("12090.00") + D("1000.00"), ANA: D("8060.00")}
    assert result.yield_total == D("150.00") + D("-100.00")
    assert [p.investment_id for p in result.positions] == ["inv_reserva", "inv_acoes"]

    later = mk.investment("inv_reserva", owners=mk.ref("split_casal"), snapshots=SNAPS,
                          movements=MOVES)  # fmt: skip
    by_user = portfolio([later], date(2026, 11, 1), splits, {}).by_user
    assert by_user == {EU: D("10445.00"), ANA: D("10445.00")}


def test_r9_5_portfolio_without_snapshot_uses_today_month_for_split() -> None:
    inv = mk.investment(owners=mk.shares((EU, 50), (ANA, 50)), movements=MOVES)
    result = portfolio([inv], date(2026, 10, 12), {}, {})
    assert result.by_user == {EU: D("10250.00"), ANA: D("10250.00")}
    assert result.yield_total == D("0.00")


def test_r9_5_closed_investment_leaves_current_total_but_stays_in_history() -> None:
    closed = mk.investment(snapshots=SNAPS, movements=MOVES, closed_at=date(2026, 11, 5))
    assert portfolio([closed], date(2026, 11, 4), {}, {}).total == D("20890.00")
    gone = portfolio([closed], date(2026, 11, 5), {}, {})
    assert gone.total == D("0.00") and gone.positions == [] and gone.by_user == {}
    hist = evolution([closed], ["2026-09", "2026-10"])
    assert hist == [("2026-09", D("20150.00"), D("20000.00")),
                    ("2026-10", D("20890.00"), D("20500.00"))]  # fmt: skip


def test_r9_6_contributions_by_goal_counts_month_contributions_only() -> None:
    linked = mk.investment(
        "inv_a",
        goal="goal_reserva",
        movements=[
            (date(2026, 10, 5), "contribution", 500),
            (date(2026, 10, 20), "contribution", 300),
            (date(2026, 10, 25), "withdrawal", 200),
            (date(2026, 11, 1), "contribution", 999),
        ],
    )
    other = mk.investment("inv_b", goal="goal_reserva",
                          movements=[(date(2026, 10, 9), "contribution", 100)])  # fmt: skip
    unlinked = mk.investment("inv_c", movements=[(date(2026, 10, 9), "contribution", 70)])
    assert contributions_by_goal([linked, other, unlinked], "2026-10") == {
        "goal_reserva": D("900.00")
    }
    assert contributions_by_goal([unlinked], "2026-10") == {}


def test_r9_5_evolution_uses_net_contributions_before_first_snapshot() -> None:
    inv = mk.investment(snapshots=SNAPS[1:], movements=MOVES)
    assert evolution([inv], ["2026-08", "2026-09", "2026-10"]) == [
        ("2026-08", D("0.00"), D("0.00")),
        ("2026-09", D("20000.00"), D("20000.00")),
        ("2026-10", D("20890.00"), D("20500.00")),
    ]
