"""R14.27: the split of a recurring expense / subscription can change from a month on
(e.g. I start sharing the household bills with my partner in January)."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code

ONLY_ANA = [{"user_id": "usr_ana", "pct": "100.00"}]
HALF = [{"user_id": "usr_ana", "pct": "50.00"}, {"user_id": "usr_bia", "pct": "50.00"}]


def _bill(world: Api, **over: Any) -> str:
    body = {
        "description": "LUZ",
        "estimated_amount": "100.00",
        "every": {"value": 1, "unit": "months"},
        "last_date": "2026-09-10",
        "payment_method": "boleto",
        "account_id": "acc_cc",
        "category_id": "cat_food",
        "group": "household",
        "allocations": ONLY_ANA,
        "allocation_history": [{"from_month": "2027-01", "allocations": HALF}],
        **over,
    }
    r = world.post("/api/recurring-purchases", body)
    assert r.status_code == 201, r.text
    return r.json()["id"]  # type: ignore[no-any-return]


def _bia_part(world: Api, month: str) -> str:
    s = world.get("/api/reports/summary", params={"month": month, "user_id": "usr_bia"}).json()
    return s["total"]  # type: ignore[no-any-return]


def test_r14_27_recurring_split_changes_from_the_month(world: Api) -> None:
    _bill(world)
    assert _bia_part(world, "2026-12") == "0.00"  # still all Ana's
    assert _bia_part(world, "2027-01") == "50.00"  # shared from January
    assert _bia_part(world, "2027-03") == "50.00"


def test_r14_27_household_payment_uses_the_split_of_its_month(world: Api) -> None:
    _bill(world)
    jan = world.get("/api/reports/household", params={"month": "2027-01"}).json()["items"][0]
    dec = world.get("/api/reports/household", params={"month": "2026-12"}).json()["items"][0]
    assert (dec["allocations"], jan["allocations"]) == (ONLY_ANA, HALF)


def test_r14_27_subscription_split_history(world: Api) -> None:
    r = world.post(
        "/api/subscriptions",
        {"description": "STREAMING", "amount": "40.00", "start_month": "2026-01",
         "card_id": "card_main", "category_id": "cat_food", "allocations": ONLY_ANA,
         "allocation_history": [{"from_month": "2027-01", "allocations": HALF}]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert _bia_part(world, "2026-12") == "0.00"
    assert _bia_part(world, "2027-01") == "20.00"


def test_r14_27_validation_and_in_use(world: Api) -> None:
    bad = [{"from_month": "2027-01", "allocations": [{"user_id": "ghost", "pct": "100.00"}]}]
    r = world.post("/api/recurring-purchases", {
        "description": "X", "estimated_amount": "1.00", "every": {"value": 1, "unit": "months"},
        "last_date": "2026-09-01", "card_id": "card_main", "allocation_history": bad})  # fmt: skip
    assert (r.status_code, error_code(r)) == (422, "reference_not_found")
    dup = [{"from_month": "2027-01", "allocations": HALF}] * 2
    r = world.post("/api/recurring-purchases", {
        "description": "X", "estimated_amount": "1.00", "every": {"value": 1, "unit": "months"},
        "last_date": "2026-09-01", "card_id": "card_main", "allocation_history": dup})  # fmt: skip
    assert r.status_code == 422
    world.create("users", {"id": "usr_cid", "name": "Cid"})
    cid = [{"user_id": "usr_cid", "pct": "100.00"}]
    _bill(world, allocation_history=[{"from_month": "2027-01", "allocations": cid}])
    r = world.delete("/api/users/usr_cid")
    assert (r.status_code, error_code(r)) == (409, "in_use")
