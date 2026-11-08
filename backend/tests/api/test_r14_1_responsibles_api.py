"""R14.1 through the API: responsibles are validated, protect users and show in balances."""

from __future__ import annotations

from api_helpers import Api, error_code

SHARED = [{"user_id": "usr_ana", "pct": "60.00"}, {"user_id": "usr_bia", "pct": "40.00"}]


def test_r14_1_account_with_several_responsibles_round_trips(world: Api) -> None:
    r = world.put(
        "/api/accounts/acc_cc",
        {
            "name": "Conta conjunta",
            "type": "checking",
            "owners": SHARED,
            "responsible_user_id": "usr_ana",
            "responsibles": SHARED,
        },
    )
    assert r.status_code == 200, r.text
    assert world.get("/api/accounts/acc_cc").json()["responsibles"] == SHARED


def test_r14_1_unknown_user_or_split_in_responsibles_is_rejected(world: Api) -> None:
    base = {"name": "X", "type": "checking", "owners": SHARED, "responsible_user_id": "usr_ana"}
    bad_user = [{"user_id": "usr_ana", "pct": "50.00"}, {"user_id": "ghost", "pct": "50.00"}]
    r = world.post("/api/accounts", {**base, "responsibles": bad_user})
    assert (r.status_code, error_code(r)) == (422, "reference_not_found")
    r = world.post("/api/accounts", {**base, "responsibles": {"split_id": "nope"}})
    assert (r.status_code, error_code(r)) == (422, "reference_not_found")


def test_r14_1_main_responsible_must_be_among_the_responsibles(world: Api) -> None:
    r = world.post(
        "/api/accounts",
        {
            "name": "X",
            "owners": SHARED,
            "responsible_user_id": "usr_ana",
            "responsibles": [{"user_id": "usr_bia", "pct": "100.00"}],
        },
    )
    assert r.status_code == 422


def test_r14_1_user_in_responsibles_cannot_be_deleted(world: Api) -> None:
    world.create("users", {"id": "usr_cid", "name": "Cid"})
    world.put(
        "/api/accounts/acc_cash",
        {
            "name": "Carteira",
            "type": "cash",
            "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
            "responsible_user_id": "usr_ana",
            "responsibles": [
                {"user_id": "usr_ana", "pct": "50.00"},
                {"user_id": "usr_cid", "pct": "50.00"},
            ],
        },
    )
    r = world.delete("/api/users/usr_cid")
    assert (r.status_code, error_code(r)) == (409, "in_use")


def test_r14_1_balances_split_the_debt_among_responsibles(world: Api) -> None:
    world.put(
        "/api/accounts/acc_cc",
        {
            "name": "Conta conjunta",
            "type": "checking",
            "owners": SHARED,
            "responsible_user_id": "usr_ana",
            "responsibles": SHARED,
        },
    )
    world.create("users", {"id": "usr_cid", "name": "Cid"})
    r = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-05",
            "amount": "100.00",
            "description": "PRESENTE",
            "category_id": "cat_food",
            "payment_method": "pix",
            "account_id": "acc_cc",
            "allocations": [{"user_id": "usr_cid", "pct": "100.00"}],
        },
    )
    assert r.status_code == 201, r.text
    bal = world.get("/api/reports/balances", params={"user_id": "usr_cid"}).json()
    nets = {p["user_id"]: p["net"] for p in bal["people"]}
    assert nets == {"usr_ana": "-60.00", "usr_bia": "-40.00"}
