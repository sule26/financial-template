"""R14.26: Contas da casa — gastos recorrentes marked as household bills: the occurrence date is
the due date, expected vs paid per month, status, and a payment that marks the bill month paid
without moving the schedule nor counting twice. Household subscriptions (first version) still
show up."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code


def _bill(world: Api, **over: Any) -> str:
    body = {
        "description": "LUZ",
        "estimated_amount": "180.00",
        "every": {"value": 1, "unit": "months"},
        "last_date": "2026-09-10",  # due on the 10th
        "payment_method": "boleto",
        "account_id": "acc_cc",
        "category_id": "cat_food",
        "group": "household",
        **over,
    }
    r = world.post("/api/recurring-purchases", body)
    assert r.status_code == 201, r.text
    return r.json()["id"]  # type: ignore[no-any-return]


def _pay(world: Api, rec_id: str, **over: Any) -> dict[str, Any]:
    body = {
        "purchase_date": "2026-10-08",
        "amount": "195.30",
        "description": "LUZ",
        "category_id": "cat_food",
        "payment_method": "boleto",
        "account_id": "acc_cc",
        "recurring_purchase_id": rec_id,
        **over,
    }
    r = world.post("/api/transactions", body)
    assert r.status_code == 201, r.text
    return r.json()["transaction"]  # type: ignore[no-any-return]


def _house(world: Api, month: str = "2026-10") -> dict[str, Any]:
    return world.get("/api/reports/household", params={"month": month}).json()  # type: ignore[no-any-return]


def test_r14_26_household_bill_status_by_due_date(world: Api) -> None:
    luz = _bill(world)  # due 10-10; today 2026-10-12 -> overdue
    agua = _bill(world, description="AGUA", estimated_amount="90.00", last_date="2026-09-25")
    _bill(world, description="RACAO", group="purchase")  # an ordinary recurring expense
    rep = _house(world)
    rows = {r["id"]: r for r in rep["items"]}
    assert set(rows) == {luz, agua}
    assert (rows[luz]["source"], rows[luz]["status"], rows[luz]["due_date"]) == (
        "recurring",
        "atrasada",
        "2026-10-10",
    )
    assert rows[agua]["status"] == "pendente"
    assert rep["totals"] == {"expected": "270.00", "paid": "0.00"}


def test_r14_26_paying_marks_the_month_and_keeps_the_schedule(world: Api) -> None:
    luz = _bill(world)
    tx = _pay(world, luz)  # paid on 10-08, before the due day
    assert tx["links"]["recurring_month"] == "2026-10"
    [row] = _house(world)["items"]
    assert (row["status"], row["paid"], row["expected"]) == ("paga", "195.30", "180.00")
    # the schedule did not move to the payment day: November is still due on the 10th
    [nov] = _house(world, "2026-11")["items"]
    assert (nov["due_date"], nov["status"]) == ("2026-11-10", "pendente")
    # no double counting: October counts the payment only, November the forecast
    oct_ = world.get("/api/reports/summary", params={"month": "2026-10"}).json()
    assert oct_["total"] == "195.30"
    nov_s = world.get("/api/reports/summary", params={"month": "2026-11"}).json()
    assert nov_s["total"] == "180.00"
    # and no "não ocorreu" alert for the paid month
    alerts = world.get("/api/alerts").json()
    assert not [a for a in alerts if a.get("recurring_id") == luz]


def test_r14_26_late_payment_and_card_payment_count_for_the_bill_month(world: Api) -> None:
    luz = _bill(world)
    _pay(world, luz, purchase_date="2026-11-02", recurring_month="2026-10")  # late
    assert [r["status"] for r in _house(world, "2026-10")["items"]] == ["paga"]
    agua = _bill(world, description="AGUA", card_id="card_main", account_id=None,
                 payment_method="credit")  # fmt: skip
    tx = _pay(world, agua, card_id="card_main", account_id=None, payment_method="credit",
              purchase_date="2026-10-10", recurring_month="2026-10")  # fmt: skip
    assert tx["invoice_month"] == "2026-11"  # after the closing on the 3rd
    statuses = {r["id"]: r["status"] for r in _house(world, "2026-10")["items"]}
    assert statuses[agua] == "paga"


def test_r14_26_paused_bill_and_bill_every_two_months(world: Api) -> None:
    _bill(world, pauses=[{"from_month": "2026-10", "until_month": None}])
    _bill(world, description="IPTU", every={"value": 2, "unit": "months"},
          last_date="2026-09-05")  # fmt: skip
    oct_rows = {r["description"]: r for r in _house(world)["items"]}
    assert (oct_rows["LUZ"]["status"], oct_rows["LUZ"]["expected"]) == ("desativada", "0.00")
    assert "IPTU" not in oct_rows  # due in November, not October
    assert "IPTU" in {r["description"] for r in _house(world, "2026-11")["items"]}


def test_r14_26_household_subscriptions_still_listed(world: Api) -> None:
    r = world.post(
        "/api/subscriptions",
        {"description": "INTERNET", "amount": "100.00", "start_month": "2026-01",
         "card_id": "card_main", "category_id": "cat_food", "group": "household",
         "due_day": 20},
    )  # fmt: skip
    sub = r.json()["id"]
    [row] = _house(world)["items"]
    assert (row["source"], row["id"], row["due_date"]) == ("subscription", sub, "2026-10-20")


def test_r14_26_validation(world: Api) -> None:
    luz = _bill(world)
    r = world.post(
        "/api/transactions",
        {"purchase_date": "2026-10-01", "amount": "1.00", "description": "X",
         "category_id": "cat_food", "card_id": "card_main", "recurring_purchase_id": luz,
         "installments": 3},
    )  # fmt: skip
    assert (r.status_code, error_code(r)) == (422, "installments_not_allowed")
    r = world.post("/api/recurring-purchases", {"description": "X", "estimated_amount": "1.00",
                   "every": {"value": 1, "unit": "months"}, "last_date": "2026-09-01",
                   "card_id": "card_main", "group": "casa"})  # fmt: skip
    assert r.status_code == 422


def test_r14_26_alert_moves_to_the_next_unpaid_bill(world: Api) -> None:
    luz = _bill(world, last_date="2026-07-25")  # due 25/08, 25/09; today 12/10
    _pay(world, luz, purchase_date="2026-08-24", recurring_month="2026-08")
    late = [a for a in world.get("/api/alerts").json() if a.get("recurring_id") == luz]
    assert [a["planned_date"] for a in late] == ["2026-09-25"]


def test_r14_26_desativar_a_bill_keeps_past_months(world: Api) -> None:
    luz = _bill(world, last_date="2026-08-10")  # September unpaid
    r = world.post(f"/api/recurring-purchases/{luz}/action", {"action": "end"})
    assert r.status_code == 200, r.text
    assert r.json()["pauses"] == [{"from_month": "2026-10", "until_month": None}]
    assert _house(world, "2026-09")["items"][0]["status"] == "atrasada"
