"""Second review of R14.26–R14.28: a conta da casa never moves its anchor, so "pending",
"Desativar", the bill a statement line pays and the split month must follow the bill months."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest
from test_review_confirm import confirm, got, staged

from conftest import ANA, FOOD, ME, World
from expense_tracker.domain.models import RecurringPurchase, ReviewInfo, Suggestion
from expense_tracker.domain.recurrence import bill_month, end, overdue
from expense_tracker.review.staging import apply_defaults, last_category_lookup

ONLY_ME = [{"user_id": ME, "pct": "100"}]
HALF = [{"user_id": ME, "pct": "50"}, {"user_id": ANA, "pct": "50"}]


def _bill(**over: object) -> RecurringPurchase:
    data: dict[str, object] = {
        "id": "rec_luz",
        "description": "LUZ",
        "estimated_amount": "180.00",
        "every": {"value": 1, "unit": "months"},
        "last_date": "2026-07-25",
        "payment_method": "boleto",
        "account_id": "acc_x",
        "group": "household",
        **over,
    }
    return RecurringPurchase.model_validate(data)


@pytest.fixture
def w(world: World) -> World:
    world.base()
    world.categorize_all(FOOD)
    return world


def test_r14_26_overdue_skips_paid_bill_months() -> None:
    today = date(2026, 10, 12)
    rec = _bill()  # due 25/08, 25/09 (10/25 still ahead)
    assert overdue(rec, today) == date(2026, 8, 25)
    assert overdue(rec, today, {"2026-08"}) == date(2026, 9, 25)
    assert overdue(rec, today, {"2026-08", "2026-09"}) is None


def test_r14_26_desativar_a_bill_never_pauses_past_months() -> None:
    today = date(2026, 10, 12)
    rec = _bill()  # August and September unpaid
    assert [p.from_month for p in end(rec, today).pauses] == ["2026-10"]
    # an ordinary recurring expense still pauses from the missed purchase
    plain = _bill(group="purchase")
    assert [p.from_month for p in end(plain, today).pauses] == ["2026-08"]


def test_r14_26_bill_month_is_the_nearest_due_date() -> None:
    rec = _bill()
    assert bill_month(rec, date(2026, 7, 20)) == "2026-07"
    assert bill_month(rec, date(2026, 9, 2)) == "2026-08"  # a late August payment
    assert bill_month(rec, date(2026, 9, 20)) == "2026-09"
    assert bill_month(rec, date(2026, 10, 30)) == "2026-10"


def _create_bill(w: World, **over: object) -> None:
    w.catalog.create(
        "recurring_purchases",
        {
            "id": "rec_luz",
            "description": "LUZ",
            "estimated_amount": "180.00",
            "every": {"value": 1, "unit": "months"},
            "last_date": "2026-08-10",
            "card_id": "card_inter",
            "group": "household",
            **over,
        },
    )


def test_r14_26_statement_line_pays_the_bill_month_without_moving_dates(w: World) -> None:
    _create_bill(w)
    staged(
        w,
        "a",
        Suggestion(type="link_recurring", target_id="rec_luz"),
        purchase_date=date(2026, 9, 11),
        amount=D("180.00"),
    )
    confirm(w, "a")
    assert w.repo.get("recurring_purchases", "rec_luz").last_date == date(2026, 8, 10)
    links = got(w, "a").links
    assert (links.recurring_purchase_id, links.recurring_month) == ("rec_luz", "2026-09")


def test_r14_27_imported_line_uses_the_split_of_the_bill_month(w: World) -> None:
    # paid on 28/12 by card -> January invoice, but it is December's bill (split changes in Jan)
    _create_bill(
        w,
        allocations=ONLY_ME,
        allocation_history=[{"from_month": "2027-01", "allocations": HALF}],
        last_date="2026-11-28",
    )
    tx = staged(
        w,
        "b",
        Suggestion(type="link_recurring", target_id="rec_luz"),
        purchase_date=date(2026, 12, 28),
        invoice_month="2027-01",
        review=ReviewInfo(suggestions=[Suggestion(type="link_recurring", target_id="rec_luz")]),
    )
    out = apply_defaults(w.repo, tx, last_category_lookup(w.repo))
    assert [(s.user_id, s.pct) for s in out.allocations] == [(ME, D("100.00"))]


def test_r14_27_ordinary_recurring_uses_the_purchase_month_split(w: World) -> None:
    _create_bill(
        w,
        group="purchase",
        allocations=ONLY_ME,
        allocation_history=[{"from_month": "2027-01", "allocations": HALF}],
        last_date="2026-11-28",
    )
    tx = staged(
        w,
        "c",
        purchase_date=date(2026, 12, 28),
        invoice_month="2027-01",
        review=ReviewInfo(suggestions=[Suggestion(type="link_recurring", target_id="rec_luz")]),
    )
    out = apply_defaults(w.repo, tx, last_category_lookup(w.repo))
    assert [(s.user_id, s.pct) for s in out.allocations] == [(ME, D("100.00"))]
