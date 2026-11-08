"""R14.22: a PIX/débito receivable takes the due date of the card linked to the account.
R14.23: a manual entry can change payment method, card or account after it was saved."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code

HALF = [{"user_id": "usr_ana", "pct": "50.00"}, {"user_id": "usr_bia", "pct": "50.00"}]


def _manual(world: Api, **over: Any) -> dict[str, Any]:
    body = {
        "purchase_date": "2026-10-05",
        "amount": "100.00",
        "description": "ALUGUEL",
        "category_id": "cat_food",
        **over,
    }
    r = world.post("/api/transactions", body)
    assert r.status_code == 201, r.text
    return r.json()["transaction"]  # type: ignore[no-any-return]


def test_r14_22_pix_receivable_uses_the_linked_card_due_date(world: Api) -> None:
    # world: card_main (closing 3, due 10) is linked to acc_cc; a PIX on 10-05 goes with the
    # invoice a card purchase that day would be on (November, due 11-10)
    _manual(world, payment_method="pix", account_id="acc_cc", allocations=HALF)
    rep = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()
    [item] = rep["items"]
    assert (item["account_id"], item["due_date"]) == ("acc_cc", "2026-11-10")


def test_r14_22_account_without_card_has_no_due_date(world: Api) -> None:
    world.create(
        "accounts",
        {
            "id": "acc_solo",
            "name": "Solo",
            "owners": HALF,
            "responsible_user_id": "usr_ana",
        },
    )
    _manual(world, payment_method="pix", account_id="acc_solo")
    [item] = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()["items"]
    assert item["due_date"] is None


def test_r14_23_move_a_manual_entry_from_pix_to_the_card(world: Api) -> None:
    tx = _manual(world, payment_method="pix", account_id="acc_cc")
    assert tx["invoice_month"] == "2026-10"
    r = world.patch(
        f"/api/transactions/{tx['id']}", {"payment_method": "credit", "card_id": "card_main"}
    )
    assert r.status_code == 200, r.text
    moved = r.json()
    assert (moved["payment_method"], moved["card_id"], moved["account_id"]) == (
        "credit",
        "card_main",
        None,
    )
    # bought on 10-05, after the closing on the 3rd: November invoice
    assert moved["invoice_month"] == "2026-11"


def test_r14_23_move_from_card_to_an_account(world: Api) -> None:
    tx = _manual(world, card_id="card_main")
    r = world.patch(
        f"/api/transactions/{tx['id']}", {"payment_method": "boleto", "account_id": "acc_cc"}
    )
    assert r.status_code == 200, r.text
    assert (r.json()["card_id"], r.json()["account_id"], r.json()["invoice_month"]) == (
        None,
        "acc_cc",
        "2026-10",
    )


def test_r14_23_invalid_targets_are_rejected(world: Api) -> None:
    tx = _manual(world, card_id="card_main")
    url = f"/api/transactions/{tx['id']}"
    r = world.patch(url, {"payment_method": "pix"})  # no account given
    assert (r.status_code, error_code(r)) == (422, "account_required")
    r = world.patch(url, {"payment_method": "benefit", "account_id": "acc_cc"})
    assert (r.status_code, error_code(r)) == (422, "method_not_allowed")
    r = world.patch(url, {"payment_method": "pix", "account_id": "acc_ghost"})
    assert (r.status_code, error_code(r)) == (422, "reference_not_found")
