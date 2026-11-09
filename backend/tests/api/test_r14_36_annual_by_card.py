"""R14.36: the annual summary also comes per card/account (benefit cards included) and says
how much of each month was spent on benefit, so totals can be shown with and without it."""

from __future__ import annotations

from typing import Any

from api_helpers import Api


def _spend(api: Api, **over: Any) -> None:
    body = {"purchase_date": "2026-10-05", "amount": "100.00", "description": "MERCADO",
            "category_id": "cat_food", "card_id": "card_main", **over}  # fmt: skip
    r = api.post("/api/transactions", body)
    assert r.status_code == 201, r.text


def test_r14_36_annual_by_card_and_benefit_spending(world: Api) -> None:
    _spend(world)
    _spend(world, amount="40.00", card_id=None, payment_method="benefit", account_id="acc_vr")
    s = world.get("/api/reports/summary", params={"month": "2026-10"}).json()
    assert sorted(s["annual_by_card"]) == [f"2026-{m:02d}" for m in range(1, 13)]
    octo = s["annual_by_card"]["2026-10"]
    assert octo["acc_vr"] == "40.00"
    assert sum(float(v) for v in octo.values()) == float(
        sum(float(v) for v in s["annual"]["2026-10"].values())
    )
    assert s["annual_benefit"]["2026-10"] == "40.00"
    assert s["annual_benefit"]["2026-01"] == "0.00"


def test_r14_37_series_has_each_month_by_category(world: Api) -> None:
    _spend(world)
    _spend(world, purchase_date="2026-09-05", amount="30.00")
    s = world.get("/api/reports/summary", params={"month": "2026-10"}).json()
    by_month = {m["month"]: m["by_category"] for m in s["series"]}
    assert by_month["2026-10"] == s["by_category"]
    assert sum(float(v) for v in by_month["2026-10"].values()) == float(s["total"])
    assert by_month["2026-01"] == {}
