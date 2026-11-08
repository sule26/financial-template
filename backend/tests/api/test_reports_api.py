"""Reports through the API: summary, projection (R1.13), month items, balances (R6.5),
investments (R9.5), alerts and /api/today."""

from __future__ import annotations

from typing import Any

import pytest
from api_helpers import Api, error_code

from expense_tracker.clock import FixedClock


def _manual(api: Api, **over: Any) -> dict[str, Any]:
    body = {
        "purchase_date": "2026-10-05",
        "amount": "100.00",
        "description": "MERCADO",
        "category_id": "cat_food",
        "card_id": "card_main",
        **over,
    }
    r = api.post("/api/transactions", {k: v for k, v in body.items() if v is not None})
    assert r.status_code == 201, r.text
    return r.json()["transaction"]  # type: ignore[no-any-return]


def _is_money(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.replace("-", "").count(".") == 1
        and len(value.split(".")[1]) == 2
    )


# ---------------------------------------------------------------- /api/today, R1.13


def test_r1_13_today_is_the_real_current_month(api: Api) -> None:
    assert api.get("/api/today").json() == {"date": "2026-10-12", "month": "2026-10"}


def test_r1_13_projection_is_12_months_from_current_month(world: Api) -> None:
    months = [m["month"] for m in world.get("/api/reports/projection").json()["months"]]
    assert len(months) == 12
    assert months[0] == "2026-10"
    assert months[-1] == "2027-09"
    assert months == sorted(months)


def test_r1_13_projection_follows_the_clock(world: Api, clock: FixedClock) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    clock.set(datetime(2027, 1, 2, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")))
    months = [m["month"] for m in world.get("/api/reports/projection").json()["months"]]
    assert (months[0], months[-1], len(months)) == ("2027-01", "2027-12", 12)
    assert world.get("/api/today").json()["month"] == "2027-01"


def test_r1_13_projection_includes_subscriptions_and_plans(world: Api) -> None:
    world.create(
        "subscriptions",
        {
            "description": "Streaming",
            "amount": "39.90",
            "card_id": "card_main",
            "start_month": "2026-01",
            "category_id": "cat_food",
        },
    )
    world.create(
        "installment-plans",
        {
            "card_id": "card_main",
            "description": "TV",
            "total_installments": 2,
            "first_invoice_month": "2026-12",
            "total_amount": "200.00",
            "category_id": "cat_food",
        },
    )
    proj = {m["month"]: m for m in world.get("/api/reports/projection").json()["months"]}
    assert proj["2026-11"]["total"] == "39.90"
    assert proj["2026-12"]["total"] == "139.90"
    assert proj["2027-02"]["total"] == "39.90"
    assert proj["2026-12"]["by_category"] == {"cat_food": "139.90"}
    assert all(_is_money(v) for v in proj["2026-12"]["by_card"].values())


def test_r1_13_projection_per_user_and_committed_income(world: Api) -> None:
    world.put(
        "/api/users/usr_ana",
        {"name": "Ana", "income_history": [{"from_month": "2026-01", "amount": "5000.00"}]},
    )
    world.create(
        "subscriptions",
        {
            "description": "Aluguel",
            "amount": "2000.00",
            "account_id": "acc_cc",
            "payment_method": "pix",
            "start_month": "2026-01",
            "category_id": "cat_food",
        },
    )
    full = world.get("/api/reports/projection").json()
    mine = world.get("/api/reports/projection", params={"user_id": "usr_ana"}).json()
    # R14.2 (changed): the projection table/total are cards only, so the PIX rent is not there…
    assert full["months"][1]["total"] == "0.00"
    assert mine["months"][1]["total"] == "0.00"
    commit = mine["committed_income"]
    assert [c["user_id"] for c in commit] == ["usr_ana"]
    first = commit[0]["months"][0]
    assert first["income"] == "5000.00"
    # …but committed income (R1.9) still counts it: 50 % of the shared account.
    assert first["spent"] == "1000.00"
    assert _is_money(first["ratio"])


# ---------------------------------------------------------------- summary


def test_summary_month_totals_series_and_annual(world: Api) -> None:
    world.create("categories", {"id": "cat_pharma", "name": "Farmácia"})
    _manual(world, purchase_date="2026-09-10", amount="100.00")  # → invoice 2026-10
    _manual(world, purchase_date="2026-09-20", amount="50.00", category_id="cat_pharma")
    _manual(
        world,
        purchase_date="2026-10-04",
        amount="70.00",
        card_id=None,
        account_id="acc_cc",
        payment_method="pix",
    )
    s = world.get("/api/reports/summary", params={"month": "2026-10"}).json()
    assert s["month"] == "2026-10"
    assert s["total"] == "220.00"
    assert s["by_category"] == {"cat_food": "170.00", "cat_pharma": "50.00"}
    assert s["by_card"]["card_main"] == "150.00"
    assert s["uncategorized_key"]
    series = s["series"]
    assert len(series) == 12
    assert series[-1]["month"] == "2026-10" and series[0]["month"] == "2025-11"
    assert series[-1]["total"] == "220.00"
    assert sorted(s["annual"]) == [f"2026-{m:02d}" for m in range(1, 13)]
    assert s["annual"]["2026-10"]["cat_pharma"] == "50.00"


def test_summary_by_user_and_payment_method(world: Api) -> None:
    _manual(world, purchase_date="2026-09-10", amount="100.00")
    _manual(
        world,
        purchase_date="2026-10-04",
        amount="30.00",
        card_id=None,
        account_id="acc_cash",
        payment_method="cash",
    )
    ana = world.get("/api/reports/summary", params={"month": "2026-10", "user_id": "usr_ana"})
    assert ana.json()["total"] == "80.00"  # 50 of the card + 30 of her cash
    credit = world.get(
        "/api/reports/summary", params={"month": "2026-10", "payment_method": "credit"}
    ).json()
    assert credit["total"] == "100.00"
    cash = world.get(
        "/api/reports/summary", params={"month": "2026-10", "payment_method": "cash"}
    ).json()
    assert cash["total"] == "30.00"


@pytest.mark.parametrize(
    "params",
    [
        {"month": "2026-13"},
        {},
        {"month": "2026-10", "payment_method": "bitcoin"},
        {"month": "outubro"},
    ],
)
def test_summary_rejects_invalid_params(world: Api, params: dict[str, str]) -> None:
    r = world.get("/api/reports/summary", params=params)
    assert r.status_code == 422
    assert error_code(r) == "validation_error"


def test_summary_includes_savings_goals(world: Api) -> None:
    world.create(
        "savings-goals",
        {"id": "goal_r", "name": "Reserva", "monthly_amount": "500.00", "user_id": "usr_ana"},
    )
    world.create(
        "investments",
        {
            "name": "Reserva",
            "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
            "goal_id": "goal_r",
            "movements": [{"date": "2026-10-05", "type": "contribution", "amount": "200.00"}],
        },
    )
    s = world.get("/api/reports/summary", params={"month": "2026-10"}).json()
    assert s["goals"]["goal_r"] == {"target": "500.00", "achieved": "200.00"}


# ---------------------------------------------------------------- month items


def test_month_items_lists_entries_with_parts(world: Api) -> None:
    tx = _manual(
        world,
        purchase_date="2026-10-04",
        amount="100.00",
        card_id=None,
        account_id="acc_cc",
        payment_method="pix",
        description="PIX FEIRA",
    )
    world.create(
        "subscriptions",
        {
            "description": "Streaming",
            "amount": "40.00",
            "card_id": "card_main",
            "start_month": "2026-01",
            "category_id": "cat_food",
        },
    )
    items = world.get("/api/reports/month-items", params={"month": "2026-10"}).json()
    by_desc = {i["description"]: i for i in items}
    pix = by_desc["PIX FEIRA"]
    assert pix["ref_id"] == tx["id"]
    assert pix["amount"] == "100.00"
    assert pix["payment_method"] == "pix"
    assert pix["provisional"] is True
    assert pix["parts"] == {"usr_ana": "50.00", "usr_bia": "50.00"}
    assert by_desc["Streaming"]["forecast"] is True
    assert world.get("/api/reports/month-items").status_code == 422


# ---------------------------------------------------------------- R6.5 balances


def test_r6_5_balances_per_person_month_and_entry(world: Api) -> None:
    tx = _manual(world, purchase_date="2026-09-10", amount="100.00", description="MERCADO")
    _manual(world, purchase_date="2026-10-05", amount="40.00", description="FARMACIA")
    bal = world.get("/api/reports/balances", params={"user_id": "usr_ana"}).json()
    assert bal["user_id"] == "usr_ana"
    [bia] = bal["people"]
    assert bia["user_id"] == "usr_bia"
    assert bia["net"] == "70.00"  # Bia owes Ana half of both purchases
    months = {m["month"]: m for m in bia["months"]}
    assert months["2026-10"]["net"] == "50.00"
    assert months["2026-10"]["lines"] == [
        {
            "ref_id": tx["id"],
            "description": "MERCADO",
            "amount": "50.00",
            "card_id": "card_main",
            "account_id": None,
            "due_date": "2026-10-10",
        }
    ]
    assert months["2026-11"]["net"] == "20.00"

    other_side = world.get("/api/reports/balances", params={"user_id": "usr_bia"}).json()
    assert other_side["people"][0]["net"] == "-70.00"


def test_r6_5_settlement_reduces_balance(world: Api) -> None:
    _manual(world, purchase_date="2026-09-10", amount="100.00")
    world.create(
        "settlements",
        {
            "from_user_id": "usr_bia",
            "to_user_id": "usr_ana",
            "amount": "50.00",
            "date": "2026-10-11",
            "month": "2026-10",
        },
    )
    bal = world.get("/api/reports/balances", params={"user_id": "usr_ana"}).json()
    [bia] = bal["people"]
    assert bia["net"] == "0.00"
    oct_ = next(m for m in bia["months"] if m["month"] == "2026-10")
    assert oct_["settlements"][0]["amount"] == "50.00"


def test_r6_5_balances_without_activity(world: Api) -> None:
    bal = world.get("/api/reports/balances", params={"user_id": "usr_ana"}).json()
    assert bal["people"] == []


def test_r6_5_balances_unknown_user(world: Api) -> None:
    r = world.get("/api/reports/balances", params={"user_id": "usr_ghost"})
    assert r.status_code == 404
    assert error_code(r) == "not_found"


# ---------------------------------------------------------------- R9.5 investments


def test_r9_5_investments_report(world: Api) -> None:
    world.create(
        "investments",
        {
            "id": "inv_cdb",
            "name": "CDB",
            "type": "fixed_income",
            "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
            "snapshots": [{"date": "2026-09-30", "balance": "1100.00"}],
            "movements": [{"date": "2026-01-10", "type": "contribution", "amount": "1000.00"}],
        },
    )
    world.create(
        "investments",
        {
            "id": "inv_acoes",
            "name": "Ações",
            "type": "stocks",
            "owners": [
                {"user_id": "usr_ana", "pct": "50.00"},
                {"user_id": "usr_bia", "pct": "50.00"},
            ],
            "snapshots": [{"date": "2026-10-01", "balance": "400.00"}],
            "movements": [{"date": "2026-03-01", "type": "contribution", "amount": "500.00"}],
        },
    )
    rep = world.get("/api/reports/investments").json()
    assert rep["total"] == "1500.00"
    assert rep["yield_total"] == "0.00"  # +100 on CDB, -100 on stocks
    assert rep["by_type"] == {"fixed_income": "1100.00", "stocks": "400.00"}
    assert rep["by_user"] == {"usr_ana": "1300.00", "usr_bia": "200.00"}
    pos = {p["investment_id"]: p for p in rep["positions"]}
    assert pos["inv_cdb"]["yield"] == "100.00"
    assert pos["inv_cdb"]["net_contributions"] == "1000.00"
    assert pos["inv_acoes"]["yield"] == "-100.00"
    assert pos["inv_cdb"]["balance_date"] == "2026-09-30"
    evo = rep["evolution"]
    assert len(evo) == 12 and evo[-1]["month"] == "2026-10"
    assert all(_is_money(e["balance"]) for e in evo)


def test_r9_5_investments_empty(api: Api) -> None:
    rep = api.get("/api/reports/investments").json()
    assert rep["total"] == "0.00"
    assert rep["positions"] == []


# ---------------------------------------------------------------- alerts


def test_alerts_empty_world(world: Api) -> None:
    assert world.get("/api/alerts").json() == []


def test_alerts_missing_invoice_for_card_with_activity(world: Api) -> None:
    _manual(world, purchase_date="2026-08-10")
    missing = [a for a in world.get("/api/alerts").json() if a["type"] == "missing_invoice"]
    assert missing
    assert {a["card_id"] for a in missing} == {"card_main"}
    assert all(a["month"] < "2026-11" for a in missing)
