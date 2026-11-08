"""R13.16 via the API: settled/remaining/status on receivables and the mark-received shortcut."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code

MARK = "/api/reports/receivables/mark-received"


def _manual(api: Api, **over: Any) -> None:
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


def _items(api: Api, user: str = "usr_ana") -> list[dict[str, Any]]:
    return api.get("/api/reports/receivables", params={"user_id": user}).json()["items"]  # type: ignore[no-any-return]


def _mark(api: Api, **over: Any) -> Any:
    body = {
        "user_id": "usr_ana",
        "counterparty_user_id": "usr_bia",
        "direction": "receive",
        "card_id": "card_main",
        "invoice_month": "2026-10",
        **over,
    }
    return api.post(MARK, body)


def test_r13_16_mark_received_partial_full_and_undo(world: Api) -> None:
    # card_main (Ana responsible, 50/50, due day 10) -> Bia owes Ana 50 on invoice 2026-10
    _manual(world)
    [item] = _items(world)
    assert (item["settled"], item["remaining"], item["status"], item["overdue"]) == (
        "0.00",
        "50.00",
        "open",
        True,
    )

    r = _mark(world, amount="20.00")
    assert r.status_code == 201, r.text
    part = r.json()
    assert {k: part[k] for k in part if k not in ("id", "origin", "warnings")} == {
        "from_user_id": "usr_bia",
        "to_user_id": "usr_ana",
        "amount": "20.00",
        "date": "2026-10-12",
        "month": "2026-10",
        "note": "Recebimento Cartão principal 10/2026",
        "card_id": "card_main",
        "account_id": None,
        "invoice_month": "2026-10",
    }
    assert part["id"].startswith("set_")
    rep = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()
    [item] = rep["items"]
    assert (item["amount"], item["settled"], item["remaining"], item["status"]) == (
        "50.00",
        "20.00",
        "30.00",
        "partial",
    )
    assert item["overdue"] is True
    assert rep["totals"] == {"receive": "30.00", "pay": "0.00"}

    rest = _mark(world).json()  # amount omitted -> what is still open
    assert rest["amount"] == "30.00"
    [item] = _items(world)
    assert (item["remaining"], item["status"], item["overdue"]) == ("0.00", "received", False)
    [bia] = _items(world, "usr_bia")  # same receivable from the payer's side
    assert (bia["direction"], bia["settled"], bia["status"]) == ("pay", "50.00", "received")

    r = _mark(world)
    assert r.status_code == 409
    assert error_code(r) == "already_received"

    # undo ("desmarcar") = delete the settlement
    assert world.delete(f"/api/settlements/{rest['id']}").status_code == 200
    [item] = _items(world)
    assert (item["remaining"], item["status"]) == ("30.00", "partial")
    # the net balance also counts the linked settlement
    bal = world.get("/api/reports/balances", params={"user_id": "usr_ana"}).json()
    assert bal["people"][0]["net"] == "30.00"


def test_r13_16_mark_paid_from_the_payer_side_and_additional_card(world: Api) -> None:
    world.create(
        "cards",
        {"id": "card_add", "name": "Adicional", "parent_card_id": "card_main",
         "last_digits": ["9999"]},
    )  # fmt: skip
    _manual(world, card_id="card_add")
    r = _mark(
        world, user_id="usr_bia", counterparty_user_id="usr_ana", direction="pay",
        card_id="card_add",
    )  # fmt: skip
    assert r.status_code == 201, r.text
    paid = r.json()
    assert (paid["from_user_id"], paid["to_user_id"], paid["card_id"]) == (
        "usr_bia",
        "usr_ana",
        "card_main",  # additional card -> main card's invoice
    )
    assert _items(world)[0]["status"] == "received"


def test_r13_16_mark_received_on_an_account(world: Api) -> None:
    _manual(world, card_id=None, account_id="acc_cc", payment_method="pix", amount="40.00")
    [item] = _items(world)
    assert (item["account_id"], item["due_date"], item["amount"]) == ("acc_cc", None, "20.00")
    r = _mark(world, card_id=None, account_id="acc_cc", invoice_month=item["invoice_month"])
    assert r.status_code == 201, r.text
    assert r.json()["note"].startswith("Recebimento Conta conjunta ")
    assert _items(world)[0]["status"] == "received"


def test_r13_16_mark_received_errors(world: Api) -> None:
    _manual(world)
    r = _mark(world, invoice_month="2026-11")
    assert r.status_code == 404
    assert error_code(r) == "receivable_not_found"
    r = _mark(world, direction="pay")
    assert r.status_code == 404
    r = _mark(world, counterparty_user_id="usr_ghost")
    assert r.status_code == 404
    assert error_code(r) == "not_found"
    r = _mark(world, amount="0.00")
    assert r.status_code == 409  # nothing to settle
    r = _mark(world, direction="maybe")
    assert r.status_code == 422
    r = _mark(world, extra=True)
    assert r.status_code == 422


def test_r13_16_settlement_link_fields_are_validated_and_protect_deletes(world: Api) -> None:
    base = {
        "from_user_id": "usr_bia",
        "to_user_id": "usr_ana",
        "amount": "10.00",
        "date": "2026-10-11",
        "month": "2026-10",
    }
    r = world.post("/api/settlements", {**base, "card_id": "card_main"})
    assert r.status_code == 422  # card without invoice_month
    r = world.post(
        "/api/settlements",
        {**base, "card_id": "card_main", "account_id": "acc_cc", "invoice_month": "2026-10"},
    )
    assert r.status_code == 422
    r = world.post("/api/settlements", {**base, "card_id": "card_x", "invoice_month": "2026-10"})
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"
    world.create("settlements", {**base, "id": "set_vr", "account_id": "acc_vr",
                                 "invoice_month": "2026-10"})  # fmt: skip
    r = world.delete("/api/accounts/acc_vr")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["referenced_by"] == ["settlements/set_vr"]
    legacy = world.create("settlements", base)  # unlinked: only the net balance
    assert (legacy["card_id"], legacy["account_id"], legacy["invoice_month"]) == (None, None, None)
