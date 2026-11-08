"""Installment plans: schedule, status, anticipation, cancellation (docs/07 "Parcelamentos")."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from expense_tracker.domain.models import Anticipation, InstallmentPlan, StatusOverride
from expense_tracker.domain.money import ZERO, split_installments
from expense_tracker.domain.months import add_months


class PlanError(ValueError):
    """Invalid operation on an installment plan."""


@dataclass(frozen=True)
class Charge:
    """One scheduled charge of a plan in an invoice month."""

    plan_id: str
    month: str
    amount: Decimal
    n: int | None  # installment number, None for the anticipation charge
    kind: Literal["installment", "anticipation"]
    range_from: int | None = None
    range_to: int | None = None


def installment_amounts(plan: InstallmentPlan) -> list[Decimal]:
    """Amount of each installment: imported plans repeat the read value; manual plans split
    ``total_amount`` with the leftover cents on the first installment."""
    if plan.installment_amount is not None and plan.origin.type == "import":
        return [plan.installment_amount] * plan.total_installments
    return split_installments(plan.total_amount, plan.total_installments)


def installment_month(plan: InstallmentPlan, n: int) -> str:
    return add_months(plan.first_invoice_month, n - 1)


def schedule(plan: InstallmentPlan) -> list[Charge]:
    """Charges of the plan, honoring cancellation and anticipation (R1.2, R7.1, R7.2)."""
    amounts = installment_amounts(plan)
    cancel_from = plan.status_override.from_n if plan.status_override else None
    ant = plan.anticipation
    charges: list[Charge] = []
    for n in range(1, plan.total_installments + 1):
        if cancel_from is not None and n >= cancel_from:
            continue
        if ant is not None and n >= ant.from_n:
            continue
        charges.append(
            Charge(plan.id, installment_month(plan, n), amounts[n - 1], n, "installment")
        )
    if ant is not None:
        last = plan.total_installments
        if cancel_from is not None:
            last = min(last, cancel_from - 1)
        if last >= ant.from_n:
            amount = (
                ant.amount if ant.amount is not None else sum(amounts[ant.from_n - 1 : last], ZERO)
            )
            charges.append(
                Charge(plan.id, ant.target_month, amount, None, "anticipation", ant.from_n, last)
            )
    return charges


PlanStatus = Literal["pago", "terminando", "em andamento", "cancelado"]


def status(plan: InstallmentPlan, current_month: str) -> PlanStatus:
    """R1.3 relative to ``H(card)``; an anticipation counts as one charge."""
    if plan.status_override is not None and plan.status_override.status == "cancelled":
        return "cancelado"
    remaining = sum(1 for c in schedule(plan) if c.month >= current_month)
    if remaining == 0:
        return "pago"
    if remaining <= 3:  # R14.19: "terminando" when 3 or fewer charges are left
        return "terminando"
    return "em andamento"


def remaining_count(plan: InstallmentPlan, current_month: str) -> int:
    """Charges still to come (an anticipation counts as one), R14.19."""
    return sum(1 for c in schedule(plan) if c.month >= current_month)


def remaining_amount(plan: InstallmentPlan, current_month: str) -> Decimal:
    return sum((c.amount for c in schedule(plan) if c.month >= current_month), ZERO)


def first_open_installment(plan: InstallmentPlan, current_month: str) -> int | None:
    for n in range(1, plan.total_installments + 1):
        if installment_month(plan, n) >= current_month:
            return n
    return None


def anticipate(
    plan: InstallmentPlan,
    *,
    current_month: str,
    imported_months: set[str],
    from_n: int | None = None,
    target_month: str | None = None,
    amount: Decimal | None = None,
) -> InstallmentPlan:
    """Return a copy of ``plan`` with an anticipation (R7.1, R7.2).

    ``target_month`` defaults to the first month ``>= H`` without an imported invoice and can
    never be ``< H``. ``from_n`` defaults to the first installment whose month is
    ``>= target_month``; an installment scheduled before the target month cannot be anticipated
    (it is charged in its own invoice, so moving it would count it twice).
    """
    if plan.status_override is not None:
        raise PlanError("cannot anticipate a cancelled plan")
    if plan.anticipation is not None and plan.anticipation.linked_fingerprints:
        raise PlanError("anticipation already matched an imported invoice")
    target = target_month
    if target is None:
        target = current_month
        while target in imported_months:
            target = add_months(target, 1)
    if target < current_month:
        raise PlanError("anticipation target month cannot be in the past")
    start = from_n if from_n is not None else first_open_installment(plan, target)
    if start is None:
        raise PlanError("plan has no installments left to anticipate")
    if not 1 <= start <= plan.total_installments:
        raise PlanError("from_n out of range")
    if installment_month(plan, start) < target:
        raise PlanError(
            f"installment {start} is due in {installment_month(plan, start)}, "
            f"before the target month {target}"
        )
    if amount is not None and amount <= 0:
        raise PlanError("anticipation amount must be positive")
    return plan.model_copy(
        update={"anticipation": Anticipation(from_n=start, target_month=target, amount=amount)}
    )


def anticipated_at_bank(plan: InstallmentPlan, from_n: int) -> InstallmentPlan:
    """docs/09 row 7 "antecipada no banco": installments ``from_n..N`` were already charged in
    real invoices (not linked to the plan), so they leave the projection. Unlike
    :func:`anticipate`, there is no H restriction: the bank already did it."""
    if not 1 <= from_n <= plan.total_installments:
        raise PlanError("from_n out of range")
    return plan.model_copy(
        update={"status_override": StatusOverride(status="anticipated_at_bank", from_n=from_n)}
    )


def undo_anticipation(plan: InstallmentPlan) -> InstallmentPlan:
    """R7.4: allowed only while no real invoice line is linked."""
    if plan.anticipation is None:
        raise PlanError("plan has no anticipation")
    if plan.anticipation.linked_fingerprints:
        raise PlanError("anticipation already matched an imported invoice")
    return plan.model_copy(update={"anticipation": None})


def cancel(plan: InstallmentPlan, from_n: int) -> InstallmentPlan:
    """Cancel installments ``from_n..N`` (R8.7)."""
    if not 1 <= from_n <= plan.total_installments:
        raise PlanError("from_n out of range")
    ant = plan.anticipation
    if ant is not None and ant.linked_fingerprints and from_n <= plan.total_installments:
        raise PlanError("cannot cancel a plan whose anticipation was already charged")

    return plan.model_copy(update={"status_override": StatusOverride(from_n=from_n)})
