"""R14.2: the projection shows only cards (main cards with their additionals, and benefit cards);
checking and cash accounts stay out of the table, the items and the total. Month items follow the
selected person (their part only)."""

from __future__ import annotations

from typing import Any

from api_helpers import Api


def _sub(api: Api, description: str, amount: str, **target: Any) -> None:
    api.create(
        "subscriptions",
        {
            "description": description,
            "amount": amount,
            "start_month": "2026-01",
            "category_id": "cat_food",
            **target,
        },
    )


def _seed(world: Api) -> None:
    # Additional card used only by Bia, billed on the main card.
    world.create(
        "cards",
        {
            "id": "card_add",
            "name": "Adicional",
            "parent_card_id": "card_main",
            "owners": [{"user_id": "usr_bia", "pct": "100.00"}],
            "last_digits": ["5678"],
        },
    )
    _sub(world, "STREAMING", "40.00", card_id="card_main")
    _sub(world, "ACADEMIA", "60.00", card_id="card_add")
    _sub(world, "ALUGUEL", "2000.00", account_id="acc_cc", payment_method="pix")
    _sub(world, "PADARIA", "30.00", account_id="acc_vr", payment_method="benefit")
    _sub(world, "FEIRA", "15.00", account_id="acc_cash", payment_method="cash")


def test_r14_2_projection_columns_are_cards_and_benefit_cards_only(world: Api) -> None:
    _seed(world)
    month = world.get("/api/reports/projection").json()["months"][1]  # 2026-11
    # additional summed on its main card; checking (acc_cc) and cash (acc_cash) left out
    assert month["by_card"] == {"card_main": "100.00", "acc_vr": "30.00"}
    assert set(month["states"]) == {"card_main", "acc_vr"}
    assert month["total"] == "130.00"
    assert month["by_category"] == {"cat_food": "130.00"}


def test_r14_2_committed_income_still_counts_account_spending(world: Api) -> None:
    _seed(world)
    world.put(
        "/api/users/usr_ana",
        {"name": "Ana", "income_history": [{"from_month": "2026-01", "amount": "5000.00"}]},
    )
    proj = world.get("/api/reports/projection", params={"user_id": "usr_ana"}).json()
    nov = next(r for r in proj["committed_income"][0]["months"] if r["month"] == "2026-11")
    # cash spending is what the person spent, wherever it went (R1.9): 50% of 40 + 50% of 2000
    # (shared acc_cc) + 15 (cash) — the card-only filter applies to the table, not to R1.9.
    assert nov["spent"] == "1035.00"


def test_r14_2_month_items_cards_only_and_by_person(world: Api) -> None:
    _seed(world)
    params = {"month": "2026-11", "cards_only": "true"}
    items = world.get("/api/reports/month-items", params=params).json()
    assert sorted(i["description"] for i in items) == ["ACADEMIA", "PADARIA", "STREAMING"]

    bia = world.get("/api/reports/month-items", params={**params, "user_id": "usr_bia"}).json()
    by_desc = {i["description"]: i for i in bia}
    # Bia's part only: half of the shared card and all of her additional; nothing from VR (Ana's)
    assert sorted(by_desc) == ["ACADEMIA", "STREAMING"]
    assert by_desc["STREAMING"]["amount"] == "20.00"
    assert by_desc["STREAMING"]["total_amount"] == "40.00"
    assert by_desc["ACADEMIA"]["amount"] == "60.00"


def test_r14_2_month_items_default_still_lists_everything(world: Api) -> None:
    _seed(world)
    items = world.get("/api/reports/month-items", params={"month": "2026-11"}).json()
    assert "ALUGUEL" in {i["description"] for i in items}
    assert all(i["total_amount"] == i["amount"] for i in items)


def test_r14_2_month_items_unknown_user_is_404(world: Api) -> None:
    r = world.get("/api/reports/month-items", params={"month": "2026-11", "user_id": "nobody"})
    assert r.status_code == 404
