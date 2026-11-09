"""R14.30 through the API: "todo dia X" is stored, and a manual purchase on another day keeps
the next ones on day X."""

from __future__ import annotations

from api_helpers import Api


def test_r14_30_manual_purchase_on_another_day_keeps_day_x(world: Api) -> None:
    r = world.post(
        "/api/recurring-purchases",
        {"description": "ACADEMIA", "estimated_amount": "100.00",
         "every": {"value": 1, "unit": "months"}, "last_date": "2026-09-10",
         "day_of_month": 10, "card_id": "card_main", "category_id": "cat_food"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["day_of_month"] == 10
    r = world.post(
        "/api/transactions",
        {"purchase_date": "2026-10-12", "amount": "100.00", "description": "ACADEMIA",
         "category_id": "cat_food", "payment_method": "credit", "card_id": "card_main",
         "recurring_purchase_id": rec["id"]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    after = world.get(f"/api/recurring-purchases/{rec['id']}").json()
    assert after["last_date"] == "2026-10-10"


def test_r14_30_day_of_month_rejected_on_days_interval(world: Api) -> None:
    r = world.post(
        "/api/recurring-purchases",
        {"description": "X", "estimated_amount": "1.00", "every": {"value": 30, "unit": "days"},
         "last_date": "2026-09-10", "day_of_month": 10, "card_id": "card_main"},
    )  # fmt: skip
    assert r.status_code == 422, r.text
