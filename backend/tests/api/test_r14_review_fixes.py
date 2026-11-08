"""Fixes from the independent review of phase 7 (R14.20, R14.22, R14.23, R14.24, R14.26)."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code


def _bill(world: Api, **over: Any) -> str:
    body = {
        "description": "LUZ",
        "amount": "180.00",
        "start_month": "2026-01",
        "card_id": "card_main",
        "category_id": "cat_food",
        "group": "household",
        "due_day": 10,
        **over,
    }
    r = world.post("/api/subscriptions", body)
    assert r.status_code == 201, r.text
    return r.json()["id"]  # type: ignore[no-any-return]


def _pay(world: Api, sub_id: str, **over: Any) -> dict[str, Any]:
    body = {
        "purchase_date": "2026-10-10",
        "amount": "180.00",
        "description": "LUZ",
        "category_id": "cat_food",
        "card_id": "card_main",
        "subscription_id": sub_id,
        **over,
    }
    r = world.post("/api/transactions", body)
    assert r.status_code == 201, r.text
    return r.json()["transaction"]  # type: ignore[no-any-return]


def _house(world: Api, month: str) -> list[dict[str, Any]]:
    return world.get("/api/reports/household", params={"month": month}).json()["items"]  # type: ignore[no-any-return]


def test_r14_26_bill_paid_by_card_counts_for_the_bill_month(world: Api) -> None:
    luz = _bill(world)
    # paid by card on 10/10 (card closes on the 3rd -> November invoice), for October's bill
    tx = _pay(world, luz, subscription_month="2026-10")
    assert tx["invoice_month"] == "2026-11"
    assert tx["links"]["subscription_month"] == "2026-10"
    assert [r["status"] for r in _house(world, "2026-10")] == ["paga"]
    nov = _house(world, "2026-11")
    assert (nov[0]["status"], nov[0]["expected"]) == ("pendente", "180.00")


def test_r14_26_late_payment_in_the_next_month(world: Api) -> None:
    luz = _bill(world, card_id=None, account_id="acc_cc", payment_method="boleto")
    _pay(
        world,
        luz,
        card_id=None,
        account_id="acc_cc",
        payment_method="boleto",
        purchase_date="2026-11-02",
        subscription_month="2026-10",
    )
    assert [r["status"] for r in _house(world, "2026-10")] == ["paga"]
    # November still expects its own bill (forecast not dropped)
    nov = world.get("/api/reports/summary", params={"month": "2026-11"}).json()
    assert nov["total"] == "360.00"  # late October payment + November forecast


def test_r14_26_bill_payment_cannot_be_installments(world: Api) -> None:
    luz = _bill(world)
    r = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-10",
            "amount": "180.00",
            "description": "LUZ",
            "category_id": "cat_food",
            "card_id": "card_main",
            "subscription_id": luz,
            "installments": 3,
        },
    )
    assert (r.status_code, error_code(r)) == (422, "installments_not_allowed")


def test_r14_22_pix_after_the_due_day_gets_the_next_due_date(world: Api) -> None:
    # card_main: closing 3, due 10. A PIX on 10-20 belongs with the invoice due 11-10.
    r = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-20",
            "amount": "100.00",
            "description": "ALUGUEL",
            "category_id": "cat_food",
            "payment_method": "pix",
            "account_id": "acc_cc",
        },
    )
    assert r.status_code == 201, r.text
    [item] = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()["items"]
    assert (item["due_date"], item["overdue"]) == ("2026-11-10", False)


def test_r14_23_moving_cash_to_pix_makes_it_provisional_again(world: Api) -> None:
    r = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-05",
            "amount": "20.00",
            "description": "FEIRA",
            "category_id": "cat_food",
            "payment_method": "cash",
            "account_id": "acc_cash",
        },
    )
    tx = r.json()["transaction"]
    assert tx["provisional"] is False
    moved = world.patch(
        f"/api/transactions/{tx['id']}", {"payment_method": "pix", "account_id": "acc_cc"}
    ).json()
    assert moved["provisional"] is True
    back = world.patch(
        f"/api/transactions/{tx['id']}", {"payment_method": "cash", "account_id": "acc_cash"}
    ).json()
    assert back["provisional"] is False


def test_r14_20_imported_plan_schedule_is_read_only(world: Api) -> None:
    r = world.post(
        "/api/installment-plans",
        {
            "card_id": "card_main",
            "description": "TV",
            "total_installments": 5,
            "first_invoice_month": "2026-08",
            "total_amount": "500.00",
            "origin": {"type": "import", "fingerprint": "fp_tv"},
        },
    )
    plan = r.json()
    url = f"/api/installment-plans/{plan['id']}"
    r = world.put(url, {**plan, "total_installments": 6})
    assert (r.status_code, error_code(r)) == (422, "imported_readonly")
    r = world.put(url, {**plan, "description": "TV sala", "category_id": "cat_food"})
    assert r.status_code == 200 and r.json()["description"] == "TV sala"
