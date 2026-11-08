"""Installment plans: schedule, status, anticipation, cancellation (docs/07)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from builders import Builders
from hypothesis import given
from hypothesis import strategies as st

from expense_tracker.domain.installments import (
    PlanError,
    anticipate,
    cancel,
    first_open_installment,
    installment_amounts,
    installment_month,
    remaining_amount,
    schedule,
    status,
    undo_anticipation,
)
from expense_tracker.domain.models import Anticipation
from expense_tracker.domain.months import add_months

D = Decimal
mk = Builders


def by_month(plan_charges: list) -> dict[str, Decimal]:  # type: ignore[type-arg]
    out: dict[str, Decimal] = {}
    for c in plan_charges:
        out[c.month] = out.get(c.month, D("0")) + c.amount
    return out


LOJA_X = mk.plan("plan_12", n=10, total=1500, first="2026-08")


# ---------------------------------------------------------------- amounts and schedule


def test_r1_2_manual_plan_first_installment_takes_leftover_cents() -> None:
    # docs/07#parcelamentos: 100,00 in 3x -> 33,34 + 33,33 + 33,33
    plan = mk.plan(n=3, total="100.00", first="2026-08")
    assert installment_amounts(plan) == [D("33.34"), D("33.33"), D("33.33")]
    charges = schedule(plan)
    assert [(c.n, c.month, c.amount) for c in charges] == [
        (1, "2026-08", D("33.34")),
        (2, "2026-09", D("33.33")),
        (3, "2026-10", D("33.33")),
    ]
    assert all(c.kind == "installment" for c in charges)


def test_r1_2_imported_plan_repeats_read_installment_value() -> None:
    # docs/07: imported plans use the PDF value for every installment
    plan = mk.plan(n=3, total="300.03", imported_amount="100.01")
    assert installment_amounts(plan) == [D("100.01")] * 3


def test_r1_2_manual_plan_ignores_installment_amount_field() -> None:
    plan = mk.plan(n=3, total="100.00").model_copy(update={"installment_amount": D("40.00")})
    assert installment_amounts(plan) == [D("33.34"), D("33.33"), D("33.33")]


def test_r1_2_single_installment_and_year_turn() -> None:
    plan = mk.plan(n=1, total="99.90", first="2026-12")
    assert [(c.n, c.month, c.amount) for c in schedule(plan)] == [(1, "2026-12", D("99.90"))]
    assert installment_month(mk.plan(n=10, first="2026-08"), 6) == "2027-01"


# ---------------------------------------------------------------- status (R1.3)


@pytest.mark.parametrize(
    ("h", "expected"),
    [
        ("2026-07", "em andamento"),
        ("2027-03", "em andamento"),  # 3 left: 03, 04, 05
        ("2027-04", "quase acabando"),  # 2 left
        ("2027-05", "quase acabando"),  # 1 left
        ("2027-06", "pago"),
    ],
)
def test_r1_3_status_relative_to_h(h: str, expected: str) -> None:
    # docs/07#status-r13
    assert status(LOJA_X, h) == expected


def test_r1_3_status_cancelled_overrides_everything() -> None:
    assert status(cancel(LOJA_X, 6), "2026-08") == "cancelado"
    assert status(cancel(LOJA_X, 6), "2030-01") == "cancelado"


def test_r1_3_anticipation_counts_as_one_charge() -> None:
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6,
                      target_month="2026-12")  # fmt: skip
    # charges >= 2026-10: 3rd(10), 4th(11), 5th(12), anticipation(12) -> 4
    assert status(plan, "2026-10") == "em andamento"
    # >= 2026-11: 4th, 5th, anticipation -> 3
    assert status(plan, "2026-11") == "em andamento"
    # >= 2026-12: 5th + anticipation -> 2
    assert status(plan, "2026-12") == "quase acabando"
    assert status(plan, "2027-01") == "pago"


# ---------------------------------------------------------------- anticipation (R7)


def test_r7_1_anticipation_moves_remaining() -> None:
    # docs/07#antecipação: 10x150 from 2026-08, anticipated from the 6th to 2026-12, no amount
    before = by_month(schedule(LOJA_X))
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6,
                      target_month="2026-12")  # fmt: skip
    after = by_month(schedule(plan))
    for month in ("2026-08", "2026-09", "2026-10", "2026-11"):
        assert before[month] == after[month] == D("150.00")
    assert before["2026-12"] == D("150.00")
    assert after["2026-12"] == D("900.00")  # 150 (5th) + 750 (6th–10th)
    for month in ("2027-01", "2027-02", "2027-03", "2027-04", "2027-05"):
        assert before[month] == D("150.00")
        assert month not in after
    ant = [c for c in schedule(plan) if c.kind == "anticipation"]
    assert len(ant) == 1
    assert (ant[0].month, ant[0].amount, ant[0].n) == ("2026-12", D("750.00"), None)
    assert (ant[0].range_from, ant[0].range_to) == (6, 10)


def test_r7_2_anticipation_with_bank_amount_uses_it() -> None:
    # docs/07#antecipação item 3: informed value replaces the sum of installments
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6,
                      target_month="2026-12", amount=D("685.00"))  # fmt: skip
    after = by_month(schedule(plan))
    assert after["2026-12"] == D("835.00")  # 150 + 685
    assert sum(after.values()) == D("1435.00")


def test_r7_1_anticipation_defaults_first_open_installment_and_first_month_without_invoice() -> (
    None
):
    # docs/07#antecipação items 1-2: target = first month >= H without an imported invoice;
    # start = first installment whose month is >= target (earlier ones stay in their invoices)
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months={"2026-10", "2026-11"})
    assert plan.anticipation == Anticipation(from_n=5, target_month="2026-12")
    assert first_open_installment(LOJA_X, "2026-10") == 3
    assert first_open_installment(LOJA_X, "2027-06") is None


def test_r7_1_anticipation_target_before_h_rejected() -> None:
    with pytest.raises(PlanError, match="past"):
        anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6,
                   target_month="2026-09")  # fmt: skip


def test_r7_1_anticipation_from_first_and_from_last_installment() -> None:
    first = anticipate(LOJA_X, current_month="2026-08", imported_months=set(), from_n=1)
    charges = schedule(first)
    assert [(c.kind, c.month, c.amount) for c in charges] == [
        ("anticipation", "2026-08", D("1500.00"))
    ]
    last = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=10)
    ant = schedule(last)[-1]
    assert (ant.kind, ant.month, ant.amount, ant.range_from, ant.range_to) == (
        "anticipation", "2026-10", D("150.00"), 10, 10,
    )  # fmt: skip
    assert len(schedule(last)) == 10


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"from_n": 0}, "out of range"),
        ({"from_n": 11}, "out of range"),
        ({"from_n": 6, "amount": D("0")}, "positive"),
        ({"from_n": 6, "amount": D("-1")}, "positive"),
    ],
)
def test_r7_1_anticipation_invalid_arguments(kwargs: dict, match: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(PlanError, match=match):
        anticipate(LOJA_X, current_month="2026-10", imported_months=set(), **kwargs)


def test_r7_1_cannot_anticipate_finished_or_cancelled_plan() -> None:
    with pytest.raises(PlanError, match="no installments left"):
        anticipate(LOJA_X, current_month="2027-06", imported_months=set())
    with pytest.raises(PlanError, match="cancelled"):
        anticipate(cancel(LOJA_X, 6), current_month="2026-10", imported_months=set())


def test_r7_1_installment_before_target_month_cannot_be_anticipated() -> None:
    # review finding: moving an installment already charged in its own invoice double counts
    with pytest.raises(PlanError, match="before the target month"):
        anticipate(LOJA_X, current_month="2026-12", imported_months=set(), from_n=1)


def test_r7_1_reanticipating_linked_plan_rejected_and_cancel_rejected() -> None:
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6,
                      target_month="2026-12")  # fmt: skip
    assert plan.anticipation is not None
    linked = plan.model_copy(update={
        "anticipation": plan.anticipation.model_copy(update={"linked_fingerprints": ["fp"]})
    })  # fmt: skip
    with pytest.raises(PlanError, match="matched"):
        anticipate(linked, current_month="2026-10", imported_months=set(), from_n=7)
    with pytest.raises(PlanError, match="already charged"):
        cancel(linked, 8)


def test_r7_4_undo_restores_original_schedule() -> None:
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6,
                      target_month="2026-12")  # fmt: skip
    restored = undo_anticipation(plan)
    assert schedule(restored) == schedule(LOJA_X)
    assert restored.anticipation is None


def test_r7_4_undo_rejected_once_linked_to_imported_invoice() -> None:
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6)
    assert plan.anticipation is not None
    linked = plan.model_copy(
        update={
            "anticipation": plan.anticipation.model_copy(update={"linked_fingerprints": ["fp"]})
        }
    )
    with pytest.raises(PlanError, match="matched"):
        undo_anticipation(linked)
    with pytest.raises(PlanError, match="no anticipation"):
        undo_anticipation(LOJA_X)


# ---------------------------------------------------------------- cancellation (R8.7)


def test_r8_7_cancel_drops_installments_from_n() -> None:
    plan = cancel(LOJA_X, 6)
    assert [c.n for c in schedule(plan)] == [1, 2, 3, 4, 5]
    assert plan.status_override is not None and plan.status_override.from_n == 6
    with pytest.raises(PlanError):
        cancel(LOJA_X, 0)
    with pytest.raises(PlanError):
        cancel(LOJA_X, 11)


def test_r8_7_cancel_after_anticipation_trims_anticipation_range() -> None:
    plan = anticipate(LOJA_X, current_month="2026-10", imported_months=set(), from_n=6,
                      target_month="2026-12")  # fmt: skip
    trimmed = cancel(plan, 9)
    ant = [c for c in schedule(trimmed) if c.kind == "anticipation"]
    assert (ant[0].range_from, ant[0].range_to, ant[0].amount) == (6, 8, D("450.00"))
    gone = cancel(plan, 6)
    assert [c.kind for c in schedule(gone)] == ["installment"] * 5


def test_remaining_amount() -> None:
    assert remaining_amount(LOJA_X, "2027-04") == D("300.00")
    assert remaining_amount(LOJA_X, "2027-06") == D("0.00")


# ---------------------------------------------------------------- properties


@given(
    n=st.integers(min_value=1, max_value=48),
    total_cents=st.integers(min_value=1, max_value=5_000_000),
    data=st.data(),
)
def test_r7_2_anticipation_without_amount_preserves_schedule_total(
    n: int, total_cents: int, data: st.DataObject
) -> None:
    plan = mk.plan(n=n, total=str(D(total_cents) / 100), first="2026-01")
    from_n = data.draw(st.integers(min_value=1, max_value=n))
    # target never later than the first anticipated installment (rule R7.1)
    latest = add_months("2026-01", from_n - 1)
    target = data.draw(st.sampled_from(sorted({"2026-01", min("2026-06", latest), latest})))
    anticipated = anticipate(
        plan, current_month="2026-01", imported_months=set(), from_n=from_n, target_month=target
    )
    total_before = sum((c.amount for c in schedule(plan)), D("0"))
    total_after = sum((c.amount for c in schedule(anticipated)), D("0"))
    assert total_before == total_after == plan.total_amount
