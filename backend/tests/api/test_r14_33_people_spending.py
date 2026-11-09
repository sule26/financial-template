"""R14.33: the Resumo shows every person's spending, with or without income configured;
``committed_income`` (Projeção) keeps only people with income."""

from __future__ import annotations

from api_helpers import Api


def test_r14_33_projection_lists_people_without_income(world: Api) -> None:
    world.put(
        "/api/users/usr_ana",
        {"name": "Ana", "income_history": [{"from_month": "2026-01", "amount": "5000.00"}]},
    )
    world.create(
        "subscriptions",
        {"description": "Aluguel", "amount": "2000.00", "account_id": "acc_cc",
         "payment_method": "pix", "start_month": "2026-01", "category_id": "cat_food"},
    )  # fmt: skip
    proj = world.get("/api/reports/projection").json()
    assert [c["user_id"] for c in proj["committed_income"]] == ["usr_ana"]
    people = {p["user_id"]: p["months"][0] for p in proj["people"]}
    assert set(people) == {"usr_ana", "usr_bia"}
    assert (people["usr_bia"]["income"], people["usr_bia"]["ratio"]) == (None, None)
    assert people["usr_bia"]["spent"] == "1000.00"  # her half of the shared account
    assert people["usr_ana"]["income"] == "5000.00"


def test_r14_33_people_follows_the_person_filter(world: Api) -> None:
    proj = world.get("/api/reports/projection", params={"user_id": "usr_bia"}).json()
    assert [p["user_id"] for p in proj["people"]] == ["usr_bia"]
