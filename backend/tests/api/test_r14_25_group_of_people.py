"""R14.25: the Summary/Projection can show a group of people (e.g. me and my wife)."""

from __future__ import annotations

from api_helpers import Api


def _seed(world: Api) -> None:
    world.create("users", {"id": "usr_cid", "name": "Cid"})
    for uid, amount in (("usr_ana", "6000.00"), ("usr_bia", "4000.00"), ("usr_cid", "1000.00")):
        user = world.get(f"/api/users/{uid}").json()
        world.put(
            f"/api/users/{uid}",
            {**user, "income_history": [{"from_month": "2026-01", "amount": amount}]},
        )
    r = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-09-20",
            "amount": "300.00",
            "description": "MERCADO",
            "category_id": "cat_food",
            "card_id": "card_main",
            "allocations": [
                {"user_id": "usr_ana", "pct": "50.00"},
                {"user_id": "usr_bia", "pct": "30.00"},
                {"user_id": "usr_cid", "pct": "20.00"},
            ],
        },
    )
    assert r.status_code == 201, r.text


def test_r14_25_summary_of_a_group_sums_their_parts_and_incomes(world: Api) -> None:
    _seed(world)
    q = {"month": "2026-10", "user_id": "usr_ana,usr_bia"}
    s = world.get("/api/reports/summary", params=q).json()
    assert s["total"] == "240.00"  # 150 + 90
    assert s["series"][-1]["income"] == "10000.00"
    one = world.get("/api/reports/summary", params={**q, "user_id": "usr_ana"}).json()
    assert one["total"] == "150.00"


def test_r14_25_projection_and_items_for_a_group(world: Api) -> None:
    _seed(world)
    proj = world.get("/api/reports/projection", params={"user_id": "usr_ana,usr_bia"}).json()
    assert {c["user_id"] for c in proj["committed_income"]} == {"usr_ana", "usr_bia"}
    items = world.get(
        "/api/reports/month-items", params={"month": "2026-10", "user_id": "usr_bia,usr_cid"}
    ).json()
    assert [i["amount"] for i in items] == ["150.00"]  # 90 + 60


def test_r14_25_unknown_person_in_the_group_is_404(world: Api) -> None:
    r = world.get("/api/reports/summary", params={"month": "2026-10", "user_id": "usr_ana,ghost"})
    assert r.status_code == 404
