"""R13.15 through the API: institutions catalog and investments.institution_id."""

from __future__ import annotations

from typing import Any

from api_helpers import Api, error_code

OWNERS = [{"user_id": "usr_ana", "pct": "100.00"}]


def _investment(**over: Any) -> dict[str, Any]:
    return {"name": "Tesouro", "type": "fixed_income", "owners": OWNERS, **over}


def test_r13_15_institutions_crud(world: Api) -> None:
    created = world.create("institutions", {"name": "XP", "type": "broker"})
    assert created["id"].startswith("inst_")
    assert created == {"id": created["id"], "name": "XP", "type": "broker"}
    default = world.create("institutions", {"name": "Outra"})
    assert default["type"] == "other"
    r = world.post("/api/institutions", {"name": "X", "type": "casino"})
    assert r.status_code == 422
    r = world.post("/api/institutions", {"name": ""})
    assert r.status_code == 422
    updated = world.put(f"/api/institutions/{created['id']}", {"name": "XP Inc", "type": "broker"})
    assert updated.json()["name"] == "XP Inc"
    listed = world.get("/api/institutions").json()
    assert {i["name"] for i in listed} == {"XP Inc", "Outra"}
    assert world.delete(f"/api/institutions/{default['id']}").json() == {"deleted": default["id"]}


def test_r13_15_investment_institution_is_an_account_or_an_institution(world: Api) -> None:
    world.create("institutions", {"id": "inst_binance", "name": "Binance", "type": "exchange"})
    by_inst = world.create("investments", _investment(institution_id="inst_binance"))
    assert by_inst["institution_id"] == "inst_binance"
    by_acc = world.create("investments", _investment(name="CDB", institution_id="acc_cash"))
    assert by_acc["institution_id"] == "acc_cash"
    legacy = world.create("investments", _investment(name="Velho", institution="Banco X"))
    assert (legacy["institution"], legacy["institution_id"]) == ("Banco X", None)
    r = world.post("/api/investments", _investment(institution_id="inst_ghost"))
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"
    assert r.json()["error"]["details"] == {"field": "institution_id", "id": "inst_ghost"}


def test_r13_15_used_institution_or_account_cannot_be_deleted(world: Api) -> None:
    world.create("institutions", {"id": "inst_prev", "name": "Previdência", "type": "pension"})
    world.create("investments", _investment(id="inv_a", institution_id="inst_prev"))
    world.create("investments", _investment(id="inv_b", institution_id="acc_cash"))
    r = world.delete("/api/institutions/inst_prev")
    assert r.status_code == 409
    assert r.json()["error"]["details"]["referenced_by"] == ["investments/inv_a"]
    r = world.delete("/api/accounts/acc_cash")
    assert r.status_code == 409
    assert "investments/inv_b" in r.json()["error"]["details"]["referenced_by"]
    assert world.delete("/api/investments/inv_a").status_code == 200
    assert world.delete("/api/institutions/inst_prev").status_code == 200
