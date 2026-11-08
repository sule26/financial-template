"""R13.11 / R13.12 through the API: collector user, receivables endpoint, split version mode."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code


def _manual(api: Api, **over: Any) -> dict[str, Any]:
    body = {
        "purchase_date": "2026-09-10",
        "amount": "100.00",
        "description": "MERCADO",
        "category_id": "cat_food",
        "card_id": "card_main",
        **over,
    }
    r = api.post("/api/transactions", body)
    assert r.status_code == 201, r.text
    return r.json()["transaction"]  # type: ignore[no-any-return]


def test_r13_11_collector_validation_and_delete_protection(world: Api) -> None:
    r = world.post("/api/users", {"id": "usr_pais", "name": "Pais", "collector_user_id": "usr_x"})
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"
    r = world.post(
        "/api/users", {"id": "usr_pais", "name": "Pais", "collector_user_id": "usr_pais"}
    )
    assert r.status_code == 422
    assert error_code(r) == "invalid_collector"
    pais = world.create("users", {"id": "usr_pais", "name": "Pais", "collector_user_id": "usr_bia"})
    assert pais["collector_user_id"] == "usr_bia"
    r = world.delete("/api/users/usr_bia")
    assert r.status_code == 409
    assert "users/usr_pais" in r.json()["error"]["details"]["referenced_by"]


def test_r13_11_receivables_endpoint(world: Api) -> None:
    # world: card_main (closing 3 / due 10) inherits acc_cc owners 50/50, Ana responsible.
    world.create("users", {"id": "usr_pais", "name": "Pais", "collector_user_id": "usr_bia"})
    _manual(world, amount="100.00")  # invoice 2026-10, due 2026-10-10: Bia owes Ana 50
    _manual(world, purchase_date="2026-10-05", amount="40.00")  # 2026-11, due 11-10: 20
    _manual(
        world,
        amount="30.00",
        description="REMEDIO",
        allocations=[{"user_id": "usr_pais", "pct": "100.00"}],
    )  # Pais owe Bia (collector), who owes it on to Ana (R13.14)
    world.create(
        "settlements",
        {
            "from_user_id": "usr_bia",
            "to_user_id": "usr_ana",
            "amount": "10.00",
            "date": "2026-10-11",
            "month": "2026-10",
        },
    )
    rep = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()
    assert rep == {
        "user_id": "usr_ana",
        "items": [
            {
                "counterparty_user_id": "usr_bia",
                "direction": "receive",
                "card_id": "card_main",
                "account_id": None,
                "invoice_month": "2026-10",
                "due_date": "2026-10-10",
                "amount": "80.00",  # 50 + 30 passed on by Bia (collector, R13.14)
                "settled": "0.00",  # the 10.00 settlement is not linked
                "remaining": "80.00",
                "status": "open",
                "overdue": True,  # clock is 2026-10-12
                "settled_month_total": "10.00",
            },
            {
                "counterparty_user_id": "usr_bia",
                "direction": "receive",
                "card_id": "card_main",
                "account_id": None,
                "invoice_month": "2026-11",
                "due_date": "2026-11-10",
                "amount": "20.00",
                "settled": "0.00",
                "remaining": "20.00",
                "status": "open",
                "overdue": False,
                "settled_month_total": "0.00",
            },
        ],
        "totals": {"receive": "100.00", "pay": "0.00"},
    }
    bia = world.get("/api/reports/receivables", params={"user_id": "usr_bia"}).json()
    assert [(i["counterparty_user_id"], i["direction"], i["amount"]) for i in bia["items"]] == [
        ("usr_ana", "pay", "80.00"),
        ("usr_pais", "receive", "30.00"),
        ("usr_ana", "pay", "20.00"),
    ]
    assert bia["totals"] == {"receive": "30.00", "pay": "100.00"}


def test_r13_11_receivables_unknown_user(world: Api) -> None:
    r = world.get("/api/reports/receivables", params={"user_id": "usr_ghost"})
    assert r.status_code == 404
    assert error_code(r) == "not_found"


def test_r13_12_split_profile_with_per_version_mode(world: Api) -> None:
    body = {
        "id": "split_casal",
        "name": "Casal",
        "members": ["usr_ana", "usr_bia"],
        "history": [
            {
                "from_month": "2026-01",
                "mode": "fixed",
                "shares": [
                    {"user_id": "usr_ana", "pct": "70.00"},
                    {"user_id": "usr_bia", "pct": "30.00"},
                ],
            },
            {"from_month": "2026-06", "mode": "income_proportional", "shares": []},
        ],
    }
    created = world.create("split-profiles", body)
    assert created["history"][1] == {
        "from_month": "2026-06",
        "mode": "income_proportional",
        "shares": [],
    }
    bad = {**body, "id": "split_bad", "history": [{"from_month": "2026-01", "mode": "fixed"}]}
    r = world.post("/api/split-profiles", bad)
    assert r.status_code == 422
