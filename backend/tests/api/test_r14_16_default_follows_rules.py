"""R14.16 (operator report): with the split on "Padrão", nobody got the part. "Padrão" now means
the same everywhere: the first matching rule, else the owners of the card/account — also for
manual entries, subscriptions and recurring expenses (resolved when reading)."""

from __future__ import annotations

from typing import Any

from api_helpers import Api

HALF = [{"user_id": "usr_ana", "pct": "50.00"}, {"user_id": "usr_bia", "pct": "50.00"}]


def _part(world: Api, user: str, month: str) -> str:
    s = world.get("/api/reports/summary", params={"month": month, "user_id": user}).json()
    return s["total"]  # type: ignore[no-any-return]


def _setup(world: Api, **rule: Any) -> None:
    r = world.post(
        "/api/cards",
        {"id": "card_me", "name": "Meu", "last_digits": ["5555"],
         "owners": [{"user_id": "usr_ana", "pct": "100.00"}], "responsible_user_id": "usr_ana",
         "billing_history": [{"from_month": "2026-01", "closing_day": 3, "due_day": 10}]},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    body = {"id": "rule_m", "priority": 10, "when": {"description_regex": "MERCADO"},
            "then": {"allocations": HALF}, **rule}  # fmt: skip
    assert world.post("/api/rules", body).status_code == 201


def test_r14_16_manual_entry_on_padrao_follows_the_matching_rule(world: Api) -> None:
    _setup(world)
    r = world.post(
        "/api/transactions",
        {"purchase_date": "2026-10-05", "amount": "100.00", "description": "MERCADO",
         "category_id": "cat_food", "card_id": "card_me", "allocations": None},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert _part(world, "usr_bia", "2026-11") == "50.00"  # was 0.00: "ninguém recebe"
    # Ana is owed Bia's half on this card
    rec = world.get("/api/reports/receivables", params={"user_id": "usr_ana"}).json()["items"]
    assert [(i["counterparty_user_id"], i["amount"]) for i in rec] == [("usr_bia", "50.00")]


def test_r14_16_subscription_and_recurring_on_padrao_follow_the_rule(world: Api) -> None:
    _setup(world)
    sub = {"description": "MERCADO CLUBE", "amount": "40.00", "start_month": "2026-01",
           "card_id": "card_me", "category_id": "cat_food"}  # fmt: skip
    world.post("/api/subscriptions", sub)
    rec = {"description": "MERCADO FEIRA", "estimated_amount": "60.00",
           "every": {"value": 1, "unit": "months"}, "last_date": "2026-11-10",
           "card_id": "card_me", "category_id": "cat_food"}  # fmt: skip
    world.post("/api/recurring-purchases", rec)
    assert _part(world, "usr_bia", "2027-01") == "50.00"  # 20 + 30


def _buy(world: Api, description: str, **over: Any) -> None:
    body = {"purchase_date": "2026-10-05", "amount": "100.00", "description": description,
            "category_id": "cat_food", "card_id": "card_me", **over}  # fmt: skip
    assert world.post("/api/transactions", body).status_code == 201


def test_r14_16_without_a_matching_rule_padrao_is_the_owners(world: Api) -> None:
    _setup(world)
    _buy(world, "PADARIA")
    assert _part(world, "usr_bia", "2026-11") == "0.00"
    assert _part(world, "usr_ana", "2026-11") == "100.00"


def test_r14_16_explicit_split_wins_over_the_rule(world: Api) -> None:
    _setup(world)
    only_ana = [{"user_id": "usr_ana", "pct": "100.00"}]
    _buy(world, "MERCADO", allocations=only_ana)
    assert _part(world, "usr_bia", "2026-11") == "0.00"


def test_r14_16_rule_with_category_condition(world: Api) -> None:
    _setup(world, when={"description_regex": "MERCADO", "category_id": "cat_pets"})
    _buy(world, "MERCADO")
    assert _part(world, "usr_bia", "2026-11") == "0.00"  # rule is for Pets only


def test_r14_16_padrao_is_frozen_when_saved_so_a_later_rule_does_not_rewrite_it(
    world: Api,
) -> None:
    _setup(world, when={"description_regex": "NADA"})  # no rule matches yet
    body = {"purchase_date": "2026-10-05", "amount": "100.00", "description": "MERCADO",
            "category_id": "cat_food", "card_id": "card_me"}  # fmt: skip
    tx = world.post("/api/transactions", body).json()["transaction"]
    assert tx["allocation_origin"] == "owners:card"  # what "Padrão" was when saved
    # a rule created afterwards does not change an entry already saved (months stay settled)
    late = {"id": "rule_late", "priority": 1, "when": {"description_regex": "MERCADO"},
            "then": {"allocations": HALF}}  # fmt: skip
    world.post("/api/rules", late)
    assert _part(world, "usr_bia", "2026-11") == "0.00"
    # choosing "Padrão" again in the edit form resolves now: the new rule applies
    r = world.patch(f"/api/transactions/{tx['id']}", {"allocations": None})
    assert r.status_code == 200, r.text
    assert r.json()["allocation_origin"] == "rule:rule_late"
    assert _part(world, "usr_bia", "2026-11") == "50.00"


def test_r14_16_installment_forecast_on_padrao_follows_rule_priority(world: Api) -> None:
    _setup(world)
    only_bia = [{"user_id": "usr_bia", "pct": "100.00"}]
    first = {"id": "rule_a", "priority": 1, "when": {"description_regex": "MERCADO"},
             "then": {"allocations": only_bia}}  # fmt: skip
    off = {"id": "rule_0", "priority": 0, "enabled": False,
           "when": {"description_regex": "MERCADO"}, "then": {"allocations": HALF}}  # fmt: skip
    assert world.post("/api/rules", first).status_code == 201
    assert world.post("/api/rules", off).status_code == 201
    body = {"purchase_date": "2026-10-05", "amount": "300.00", "description": "MERCADO TV",
            "category_id": "cat_food", "card_id": "card_me", "installments": 3}  # fmt: skip
    r = world.post("/api/transactions", body)
    assert r.status_code == 201, r.text
    assert "plan" in r.json()
    # the plan's installments follow rule_a (priority 1), not the disabled rule_0 nor rule_m (10)
    assert _part(world, "usr_bia", "2026-12") == "100.00"
    assert _part(world, "usr_ana", "2026-12") == "0.00"
