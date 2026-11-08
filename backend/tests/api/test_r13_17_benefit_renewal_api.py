"""R13.17 through the API: benefit accounts carry a renewal day; other types reject it."""

from __future__ import annotations

from api_helpers import Api

OWNERS = [{"user_id": "usr_ana", "pct": "100.00"}]


def test_r13_17_benefit_account_saves_renewal_day(world: Api) -> None:
    body = {
        "name": "VA",
        "type": "benefit",
        "owners": OWNERS,
        "responsible_user_id": "usr_ana",
        "renewal_day": 5,
    }
    created = world.create("accounts", body)
    assert created["renewal_day"] == 5
    listed = {a["id"]: a for a in world.get("/api/accounts").json()}
    assert listed[created["id"]]["renewal_day"] == 5
    assert listed["acc_cc"]["renewal_day"] is None


def test_r13_17_renewal_day_on_checking_account_is_rejected(world: Api) -> None:
    r = world.post(
        "/api/accounts",
        {
            "name": "Banco",
            "type": "checking",
            "owners": OWNERS,
            "responsible_user_id": "usr_ana",
            "renewal_day": 5,
        },
    )
    assert r.status_code == 422
    assert "renewal_day" in r.text
