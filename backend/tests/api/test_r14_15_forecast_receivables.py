"""R14.15: "A receber" also lists what people are expected to owe from forecasts
(subscriptions, recurring purchases, installments split with them), apart from real debts."""

from __future__ import annotations

from api_helpers import Api

HALF = [{"user_id": "usr_ana", "pct": "50.00"}, {"user_id": "usr_bia", "pct": "50.00"}]


def _sub(world: Api) -> None:
    world.create(
        "subscriptions",
        {
            "description": "STREAMING",
            "amount": "40.00",
            "start_month": "2026-01",
            "card_id": "card_main",
            "category_id": "cat_food",
            "allocations": HALF,
        },
    )


def test_r14_15_shared_subscription_shows_as_forecast_to_receive(world: Api) -> None:
    _sub(world)
    body = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()
    forecast = body["forecast"]
    months = [i["invoice_month"] for i in forecast["items"]]
    # this month and the next 2 (no invoice imported yet), one item per month
    assert months == ["2026-10", "2026-11", "2026-12"]
    first = forecast["items"][0]
    assert (first["counterparty_user_id"], first["direction"], first["amount"]) == (
        "usr_bia",
        "receive",
        "20.00",
    )
    assert first["card_id"] == "card_main" and first["due_date"] == "2026-10-10"
    assert forecast["totals"] == {"receive": "60.00", "pay": "0.00"}
    # forecasts are not real debts: the confirmed side stays empty
    assert body["items"] == [] and body["totals"] == {"receive": "0.00", "pay": "0.00"}


def test_r14_15_debtor_sees_the_forecast_to_pay(world: Api) -> None:
    _sub(world)
    forecast = world.get("/api/reports/receivables", params={"user_id": "usr_bia"}).json()[
        "forecast"
    ]
    assert {i["direction"] for i in forecast["items"]} == {"pay"}
    assert forecast["totals"]["pay"] == "60.00"


def test_r14_15_real_purchases_are_not_repeated_as_forecast(world: Api) -> None:
    r = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-05",
            "amount": "100.00",
            "description": "MERCADO",
            "category_id": "cat_food",
            "card_id": "card_main",
            "allocations": HALF,
        },
    )
    assert r.status_code == 201, r.text
    body = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()
    assert body["forecast"]["items"] == []
    assert body["totals"]["receive"] == "50.00"
