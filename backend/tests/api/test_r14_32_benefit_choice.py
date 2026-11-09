"""R14.32: on a benefit card with several benefits (Caju with VR and Home office), a manual
entry says which benefit paid it."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code


def _benefit(api: Api, bid: str, name: str, **over: Any) -> None:
    body = {"id": bid, "name": name, "user_id": "usr_ana", "destination": "card",
            "account_id": "acc_vr", "amount_history": [], **over}  # fmt: skip
    r = api.post("/api/benefits", body)
    assert r.status_code == 201, r.text


def _entry(api: Api, **over: Any) -> Any:
    body = {"purchase_date": "2026-10-05", "amount": "30.00", "description": "ALMOCO",
            "category_id": "cat_food", "payment_method": "benefit", "account_id": "acc_vr",
            **over}  # fmt: skip
    return api.post("/api/transactions", body)


def test_r14_32_entry_keeps_the_chosen_benefit(world: Api) -> None:
    _benefit(world, "ben_vr", "VR")
    _benefit(world, "ben_ho", "Home office")
    r = _entry(world, benefit_id="ben_ho")
    assert r.status_code == 201, r.text
    tx = r.json()["transaction"]
    assert tx["benefit_id"] == "ben_ho"
    # changed later to VR
    r = world.patch(f"/api/transactions/{tx['id']}", {"benefit_id": "ben_vr"})
    assert r.status_code == 200, r.text
    assert r.json()["benefit_id"] == "ben_vr"
    # the benefit is in use: it cannot be deleted under the entry
    assert world.delete("/api/benefits/ben_vr").status_code == 409


def test_r14_32_benefit_must_belong_to_that_card(world: Api) -> None:
    _benefit(world, "ben_cc", "Auxílio", destination="account", account_id="acc_cc")
    assert error_code(_entry(world, benefit_id="ben_cc")) == "invalid_benefit"
    assert error_code(_entry(world, benefit_id="ben_nope")) == "invalid_benefit"
    r = _entry(world, payment_method="pix", account_id="acc_cc", benefit_id="ben_cc")
    assert error_code(r) == "invalid_benefit"


def test_r14_32_moving_off_the_benefit_card_clears_the_benefit(world: Api) -> None:
    _benefit(world, "ben_vr", "VR")
    tx = _entry(world, benefit_id="ben_vr").json()["transaction"]
    r = world.patch(
        f"/api/transactions/{tx['id']}", {"payment_method": "pix", "account_id": "acc_cc"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["benefit_id"] is None


def test_r14_32_subscription_and_recurring_say_which_benefit_pays(world: Api) -> None:
    _benefit(world, "ben_vr", "VR")
    _benefit(world, "ben_ho", "Home office")
    sub = world.post(
        "/api/subscriptions",
        {"description": "INTERNET", "amount": "100.00", "start_month": "2026-01",
         "payment_method": "benefit", "account_id": "acc_vr", "category_id": "cat_food",
         "benefit_id": "ben_ho"},
    )  # fmt: skip
    assert sub.status_code == 201, sub.text
    assert sub.json()["benefit_id"] == "ben_ho"
    rec = world.post(
        "/api/recurring-purchases",
        {"description": "ALMOCO", "estimated_amount": "30.00",
         "every": {"value": 1, "unit": "weeks"}, "last_date": "2026-10-05",
         "payment_method": "benefit", "account_id": "acc_vr", "benefit_id": "ben_vr"},
    )  # fmt: skip
    assert rec.status_code == 201, rec.text
    assert world.delete("/api/benefits/ben_ho").status_code == 409  # in use by the subscription
    # a benefit of another place, or on a non-benefit payment, is refused
    bad = world.post(
        "/api/subscriptions",
        {"description": "X", "amount": "1.00", "start_month": "2026-01", "payment_method": "pix",
         "account_id": "acc_cc", "benefit_id": "ben_vr"},
    )  # fmt: skip
    assert bad.status_code == 422
    _benefit(world, "ben_cc", "Auxílio", destination="account", account_id="acc_cc")
    wrong = world.post(
        "/api/subscriptions",
        {"description": "X", "amount": "1.00", "start_month": "2026-01",
         "payment_method": "benefit", "account_id": "acc_vr", "benefit_id": "ben_cc"},
    )  # fmt: skip
    assert error_code(wrong) == "invalid_benefit"
