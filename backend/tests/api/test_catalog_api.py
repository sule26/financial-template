"""Catalog CRUD over every resource of PATHS, referential integrity (docs/04 inv. 3 and 5),
cards (additional, last digits) and category removal (R1.11, R1.12)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from api_helpers import Api, error_code

from expense_tracker.services.errors import new_id

SHARED = [{"user_id": "usr_ana", "pct": "60.00"}, {"user_id": "usr_bia", "pct": "40.00"}]
BAD_SUM = [{"user_id": "usr_ana", "pct": "60.00"}, {"user_id": "usr_bia", "pct": "30.00"}]


def _card(last: str = "9999") -> dict[str, Any]:
    return {
        "name": "Cartão B",
        "account_id": "acc_cc",
        "last_digits": [last],
        "billing_history": [{"from_month": "2026-01", "closing_day": 25, "due_day": 5}],
    }


# Each case: (path, prefix, valid body, field to update + new value, invalid body + code).
Case = tuple[str, str, Callable[[], dict[str, Any]], tuple[str, Any], Callable[[], dict[str, Any]]]

CASES: list[Case] = [
    (
        "users",
        "usr",
        lambda: {"name": "Carla"},
        ("name", "Carla S."),
        lambda: {"name": "C", "income_history": [{"from_month": "2026-01", "amount": 1500.5}]},
    ),
    (
        "split-profiles",
        "split",
        lambda: {
            "name": "Casal",
            "members": ["usr_ana", "usr_bia"],
            "history": [{"from_month": "2026-01", "shares": SHARED}],
        },
        ("name", "Casal 2"),
        lambda: {
            "name": "Casal",
            "members": ["usr_ana", "usr_bia"],
            "history": [{"from_month": "2026-01", "shares": BAD_SUM}],
        },
    ),
    (
        "accounts",
        "acc",
        lambda: {"name": "Conta B", "owners": SHARED, "responsible_user_id": "usr_bia"},
        ("name", "Conta B2"),
        lambda: {"name": "Conta B", "owners": BAD_SUM, "responsible_user_id": "usr_bia"},
    ),
    (
        "cards",
        "card",
        _card,
        ("name", "Cartão B2"),
        lambda: {**_card(), "limit": 1000.5},
    ),
    (
        "categories",
        "cat",
        lambda: {"name": "Mercado", "budget": "800.00"},
        ("color", "#FF0000"),
        lambda: {"name": "Mercado", "budget": 800.0},
    ),
    (
        "savings-goals",
        "goal",
        lambda: {"name": "Viagem", "monthly_amount": "300.00", "user_id": "usr_ana"},
        ("monthly_amount", "350.00"),
        lambda: {"name": "Viagem", "monthly_amount": 300.25},
    ),
    (
        "subscriptions",
        "sub",
        lambda: {
            "description": "Streaming",
            "amount": "39.90",
            "card_id": "card_main",
            "start_month": "2026-01",
            "category_id": "cat_food",
        },
        ("amount", "44.90"),
        lambda: {
            "description": "Streaming",
            "amount": 39.9,
            "card_id": "card_main",
            "start_month": "2026-01",
        },
    ),
    (
        "recurring-purchases",
        "rec",
        lambda: {
            "description": "Ração",
            "estimated_amount": "180.00",
            "every": {"value": 45},
            "last_date": "2026-09-20",
            "card_id": "card_main",
            "category_id": "cat_pets",
        },
        ("estimated_amount", "190.00"),
        lambda: {
            "description": "Ração",
            "estimated_amount": 180.0,
            "every": {"value": 45},
            "last_date": "2026-09-20",
            "card_id": "card_main",
        },
    ),
    (
        "installment-plans",
        "plan",
        lambda: {
            "card_id": "card_main",
            "description": "Geladeira",
            "total_installments": 10,
            "first_invoice_month": "2026-10",
            "total_amount": "3000.00",
            "category_id": "cat_food",
        },
        ("description", "Geladeira Frost"),
        lambda: {
            "card_id": "card_main",
            "description": "Geladeira",
            "total_installments": 10,
            "first_invoice_month": "2026-10",
            "total_amount": 3000.0,
        },
    ),
    (
        "rules",
        "rule",
        lambda: {"when": {"description_regex": "IFOOD"}, "then": {"category_id": "cat_food"}},
        ("priority", 5),
        lambda: {"when": {"description_regex": "IFOOD"}, "then": {"allocations": BAD_SUM}},
    ),
    (
        "settlements",
        "set",
        lambda: {
            "from_user_id": "usr_bia",
            "to_user_id": "usr_ana",
            "amount": "50.00",
            "date": "2026-10-05",
            "month": "2026-10",
        },
        ("note", "pix"),
        lambda: {
            "from_user_id": "usr_bia",
            "to_user_id": "usr_ana",
            "amount": 50.0,
            "date": "2026-10-05",
            "month": "2026-10",
        },
    ),
    (
        "investments",
        "inv",
        lambda: {
            "name": "CDB",
            "type": "fixed_income",
            "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
            "snapshots": [{"date": "2026-09-30", "balance": "1000.00"}],
        },
        ("institution", "Banco X"),
        lambda: {
            "name": "CDB",
            "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
            "snapshots": [{"date": "2026-09-30", "balance": 1000.0}],
        },
    ),
]

IDS = [c[0] for c in CASES]


@pytest.mark.parametrize(("path", "prefix", "body", "change", "invalid"), CASES, ids=IDS)
def test_r1_crud_full_cycle(
    world: Api,
    path: str,
    prefix: str,
    body: Callable[[], dict[str, Any]],
    change: tuple[str, Any],
    invalid: Callable[[], dict[str, Any]],
) -> None:
    created = world.create(path, body())
    item_id = created["id"]
    assert item_id.startswith(f"{prefix}_")
    assert len(item_id) == len(prefix) + 1 + 26

    listed = world.get(f"/api/{path}").json()
    assert item_id in [i["id"] for i in listed]
    assert world.get(f"/api/{path}/{item_id}").json() == created

    field, value = change
    r = world.put(f"/api/{path}/{item_id}", {**body(), field: value})
    assert r.status_code == 200, r.text
    assert r.json()[field] == value
    assert r.json()["id"] == item_id
    assert world.get(f"/api/{path}/{item_id}").json()[field] == value

    # already exists
    r = world.post(f"/api/{path}", {**body(), "id": item_id})
    assert r.status_code == 409
    assert error_code(r) == "already_exists"

    # validation: float money / pct sum != 100
    r = world.post(f"/api/{path}", invalid())
    assert r.status_code == 422, r.text
    assert error_code(r) == "validation_error"
    r = world.put(f"/api/{path}/{item_id}", invalid())
    assert r.status_code == 422
    assert world.get(f"/api/{path}/{item_id}").json()[field] == value

    r = world.delete(f"/api/{path}/{item_id}")
    assert r.status_code == 200
    assert world.get(f"/api/{path}/{item_id}").status_code == 404


@pytest.mark.parametrize(("path", "prefix", "body", "change", "invalid"), CASES, ids=IDS)
def test_r1_crud_not_found(
    world: Api,
    path: str,
    prefix: str,
    body: Callable[[], dict[str, Any]],
    change: tuple[str, Any],
    invalid: Callable[[], dict[str, Any]],
) -> None:
    missing = f"/api/{path}/{prefix}_missing"
    for r in (world.get(missing), world.put(missing, body()), world.delete(missing)):
        assert r.status_code == 404
        assert error_code(r) == "not_found"


def test_r1_money_is_returned_as_two_decimal_string(world: Api) -> None:
    sub = world.create(
        "subscriptions",
        {"description": "X", "amount": "10", "card_id": "card_main", "start_month": "2026-01"},
    )
    assert sub["amount"] == "10.00"


def test_r1_money_with_three_decimals_is_rejected(world: Api) -> None:
    r = world.post("/api/categories", {"name": "X", "budget": "1.005"})
    assert r.status_code == 422


def test_r1_unknown_fields_are_rejected(world: Api) -> None:
    r = world.post("/api/users", {"name": "X", "is_admin": True})
    assert r.status_code == 422
    assert error_code(r) == "validation_error"


def test_new_id_is_prefixed_unique_and_sortable() -> None:
    ids = [new_id("tx") for _ in range(50)]
    assert len(set(ids)) == 50
    assert all(i.startswith("tx_") and len(i) == 29 for i in ids)


# ---------------------------------------------------------------- referential integrity (inv. 3)


@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        (
            "accounts",
            {
                "name": "X",
                "owners": [{"user_id": "usr_ghost", "pct": "100.00"}],
                "responsible_user_id": "usr_ana",
            },
            "owners.user_id",
        ),
        (
            "accounts",
            {
                "name": "X",
                "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
                "responsible_user_id": "usr_ghost",
            },
            "responsible_user_id",
        ),
        ("cards", {**_card(), "account_id": "acc_ghost"}, "account_id"),
        (
            "split-profiles",
            {
                "name": "S",
                "members": ["usr_ana", "usr_ghost"],
                "history": [
                    {
                        "from_month": "2026-01",
                        "shares": [
                            {"user_id": "usr_ana", "pct": "50.00"},
                            {"user_id": "usr_ghost", "pct": "50.00"},
                        ],
                    }
                ],
            },
            "members",
        ),
        (
            "savings-goals",
            {"name": "G", "monthly_amount": "1.00", "user_id": "usr_ghost"},
            "user_id",
        ),
        (
            "subscriptions",
            {
                "description": "S",
                "amount": "1.00",
                "card_id": "card_ghost",
                "start_month": "2026-01",
            },
            "card_id",
        ),
        (
            "subscriptions",
            {
                "description": "S",
                "amount": "1.00",
                "card_id": "card_main",
                "start_month": "2026-01",
                "category_id": "cat_ghost",
            },
            "category_id",
        ),
        (
            "subscriptions",
            {
                "description": "S",
                "amount": "1.00",
                "card_id": "card_main",
                "start_month": "2026-01",
                "allocations": {"split_id": "split_ghost"},
            },
            "allocations.split_id",
        ),
        (
            "recurring-purchases",
            {
                "description": "R",
                "estimated_amount": "1.00",
                "every": {"value": 30},
                "last_date": "2026-09-01",
                "account_id": "acc_ghost",
            },
            "account_id",
        ),
        (
            "installment-plans",
            {
                "card_id": "card_ghost",
                "description": "P",
                "total_installments": 2,
                "first_invoice_month": "2026-10",
                "total_amount": "10.00",
            },
            "card_id",
        ),
        (
            "rules",
            {"when": {"card_id": "card_ghost"}, "then": {"category_id": "cat_food"}},
            "when.card_id",
        ),
        (
            "rules",
            {"when": {"account_id": "acc_ghost"}, "then": {"category_id": "cat_food"}},
            "when.account_id",
        ),
        (
            "rules",
            {"when": {"category_id": "cat_ghost"}, "then": {"category_id": "cat_food"}},
            "when.category_id",
        ),
        ("rules", {"then": {"category_id": "cat_ghost"}}, "then.category_id"),
        (
            "rules",
            {"then": {"allocations": [{"user_id": "usr_ghost", "pct": "100.00"}]}},
            "then.allocations.user_id",
        ),
        (
            "settlements",
            {
                "from_user_id": "usr_ghost",
                "to_user_id": "usr_ana",
                "amount": "1.00",
                "date": "2026-10-01",
                "month": "2026-10",
            },
            "from_user_id",
        ),
        (
            "investments",
            {
                "name": "I",
                "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
                "goal_id": "goal_ghost",
            },
            "goal_id",
        ),
        (
            "investments",
            {
                "name": "I",
                "owners": [{"user_id": "usr_ana", "pct": "100.00"}],
                "account_id": "acc_ghost",
            },
            "account_id",
        ),
    ],
)
def test_r1_reference_to_missing_id_is_rejected(
    world: Api, path: str, body: dict[str, Any], field: str
) -> None:
    r = world.post(f"/api/{path}", body)
    assert r.status_code == 422, r.text
    assert error_code(r) == "reference_not_found"
    assert field.split(".")[0] in r.json()["error"]["message"]


def test_r1_reference_check_also_applies_on_update(world: Api) -> None:
    r = world.put(
        "/api/accounts/acc_cc",
        {
            "name": "X",
            "owners": [{"user_id": "usr_ghost", "pct": "100.00"}],
            "responsible_user_id": "usr_ana",
        },
    )
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"


def test_r1_rule_with_invalid_regex_is_rejected(world: Api) -> None:
    r = world.post(
        "/api/rules", {"when": {"description_regex": "("}, "then": {"category_id": "cat_food"}}
    )
    assert r.status_code == 422
    assert error_code(r) == "invalid_regex"


def test_r1_rule_without_effect_is_rejected(world: Api) -> None:
    r = world.post("/api/rules", {"when": {"description_regex": "X"}})
    assert r.status_code == 422
    assert error_code(r) == "empty_rule"


@pytest.mark.parametrize(
    ("path", "item_id", "ref"),
    [
        ("users", "usr_ana", "accounts/acc_cc"),
        ("users", "usr_bia", "accounts/acc_cc"),
        ("accounts", "acc_cc", "cards/card_main"),
    ],
)
def test_r1_delete_referenced_item_is_conflict(
    world: Api, path: str, item_id: str, ref: str
) -> None:
    r = world.delete(f"/api/{path}/{item_id}")
    assert r.status_code == 409
    assert error_code(r) == "in_use"
    assert ref in r.json()["error"]["details"]["referenced_by"]
    assert world.get(f"/api/{path}/{item_id}").status_code == 200


def test_r1_delete_user_in_split_profile_or_settlement_is_conflict(world: Api) -> None:
    world.create("users", {"id": "usr_caio", "name": "Caio"})
    world.create(
        "split-profiles",
        {
            "id": "split_x",
            "name": "S",
            "members": ["usr_ana", "usr_caio"],
            "history": [
                {
                    "from_month": "2026-01",
                    "shares": [
                        {"user_id": "usr_ana", "pct": "50.00"},
                        {"user_id": "usr_caio", "pct": "50.00"},
                    ],
                }
            ],
        },
    )
    r = world.delete("/api/users/usr_caio")
    assert r.status_code == 409
    assert "split_profiles/split_x" in r.json()["error"]["details"]["referenced_by"]

    world.delete("/api/split-profiles/split_x")
    world.create(
        "settlements",
        {
            "id": "set_1",
            "from_user_id": "usr_caio",
            "to_user_id": "usr_ana",
            "amount": "5.00",
            "date": "2026-10-01",
            "month": "2026-10",
        },
    )
    r = world.delete("/api/users/usr_caio")
    assert r.status_code == 409
    assert "settlements/set_1" in r.json()["error"]["details"]["referenced_by"]
    world.delete("/api/settlements/set_1")
    assert world.delete("/api/users/usr_caio").status_code == 200


def test_r1_delete_split_profile_in_use_by_rule_is_conflict(world: Api) -> None:
    world.create(
        "split-profiles",
        {
            "id": "split_c",
            "name": "Casal",
            "members": ["usr_ana", "usr_bia"],
            "history": [{"from_month": "2026-01", "shares": SHARED}],
        },
    )
    world.create("rules", {"id": "rule_c", "then": {"allocations": {"split_id": "split_c"}}})
    r = world.delete("/api/split-profiles/split_c")
    assert r.status_code == 409
    assert "rules/rule_c" in r.json()["error"]["details"]["referenced_by"]


def test_r1_delete_card_in_use_by_transaction_is_conflict(world: Api) -> None:
    r = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-05",
            "amount": "10.00",
            "description": "PADARIA",
            "category_id": "cat_food",
            "card_id": "card_main",
        },
    )
    tx_id = r.json()["transaction"]["id"]
    r = world.delete("/api/cards/card_main")
    assert r.status_code == 409
    assert error_code(r) == "in_use"
    assert f"transactions/{tx_id}" in r.json()["error"]["details"]["referenced_by"]


def test_r1_delete_card_in_use_by_rule_or_plan_is_conflict(world: Api) -> None:
    world.create("cards", {**_card("4444"), "id": "card_b"})
    world.create(
        "rules",
        {"id": "rule_b", "when": {"card_id": "card_b"}, "then": {"category_id": "cat_food"}},
    )
    r = world.delete("/api/cards/card_b")
    assert r.status_code == 409
    assert "rules/rule_b" in r.json()["error"]["details"]["referenced_by"]
    world.delete("/api/rules/rule_b")
    world.create(
        "installment-plans",
        {
            "id": "plan_b",
            "card_id": "card_b",
            "description": "P",
            "total_installments": 2,
            "first_invoice_month": "2026-10",
            "total_amount": "10.00",
        },
    )
    r = world.delete("/api/cards/card_b")
    assert r.status_code == 409
    assert "installment_plans/plan_b" in r.json()["error"]["details"]["referenced_by"]


def test_r1_unreferenced_user_can_be_deleted(world: Api) -> None:
    world.create("users", {"id": "usr_x", "name": "X"})
    assert world.delete("/api/users/usr_x").json() == {"deleted": "usr_x"}


# ---------------------------------------------------------------- cards (inv. 5)


def test_r1_additional_card_inherits_from_main(world: Api) -> None:
    extra = world.create(
        "cards",
        {
            "id": "card_add",
            "name": "Adicional",
            "parent_card_id": "card_main",
            "last_digits": ["5678"],
        },
    )
    assert extra["parent_card_id"] == "card_main"
    r = world.delete("/api/cards/card_main")
    assert r.status_code == 409
    assert "cards/card_add" in r.json()["error"]["details"]["referenced_by"]


def test_r1_additional_card_with_missing_parent_is_rejected(world: Api) -> None:
    r = world.post(
        "/api/cards", {"name": "A", "parent_card_id": "card_ghost", "last_digits": ["5678"]}
    )
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"


def test_r1_additional_card_of_additional_card_is_rejected(world: Api) -> None:
    world.create(
        "cards",
        {"id": "card_add", "name": "A", "parent_card_id": "card_main", "last_digits": ["5678"]},
    )
    r = world.post(
        "/api/cards", {"name": "B", "parent_card_id": "card_add", "last_digits": ["5679"]}
    )
    assert r.status_code == 422
    assert error_code(r) == "invalid_parent"


def test_r1_card_cannot_be_its_own_parent(world: Api) -> None:
    r = world.put(
        "/api/cards/card_main",
        {"name": "X", "parent_card_id": "card_main", "last_digits": ["1234"]},
    )
    assert r.status_code == 422
    assert error_code(r) == "invalid_parent"


def test_r1_main_card_without_billing_is_rejected(world: Api) -> None:
    r = world.post("/api/cards", {"name": "X", "account_id": "acc_cc", "last_digits": ["1111"]})
    assert r.status_code == 422


def test_r1_duplicate_last_digits_are_rejected(world: Api) -> None:
    r = world.post("/api/cards", _card("1234"))
    assert r.status_code == 422
    assert error_code(r) == "duplicate_last_digits"


def test_r1_card_without_resolvable_owners_is_rejected(world: Api) -> None:
    """docs/04 inv. 5: after inheritance every card has valid owners and a responsible."""
    body = {
        "name": "Sem dono",
        "last_digits": ["7777"],
        "billing_history": [{"from_month": "2026-01", "closing_day": 1, "due_day": 8}],
    }
    r = world.post("/api/cards", body)
    assert r.status_code == 422
    assert error_code(r) == "ownership_unresolved"


def test_r1_card_with_own_owners_and_responsible_is_accepted(world: Api) -> None:
    body = {
        "name": "Próprio",
        "last_digits": ["7777"],
        "owners": [{"user_id": "usr_bia", "pct": "100.00"}],
        "responsible_user_id": "usr_bia",
        "billing_history": [{"from_month": "2026-01", "closing_day": 1, "due_day": 8}],
    }
    assert world.create("cards", body)["responsible_user_id"] == "usr_bia"


def test_r1_last_digits_must_be_four_digits(world: Api) -> None:
    r = world.post("/api/cards", _card("12a4"))
    assert r.status_code == 422


# ---------------------------------------------------------------- categories (R1.11, R1.12)


def _uncat_alert(api: Api) -> dict[str, Any] | None:
    return next((a for a in api.get("/api/alerts").json() if a["type"] == "uncategorized"), None)


def test_r1_12_delete_category_in_use_uncategorizes_items(world: Api) -> None:
    world.create("categories", {"id": "cat_x", "name": "Lazer"})
    tx = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-05",
            "amount": "80.00",
            "description": "CINEMA",
            "category_id": "cat_x",
            "card_id": "card_main",
        },
    ).json()["transaction"]
    sub = world.create(
        "subscriptions",
        {
            "description": "Streaming",
            "amount": "39.90",
            "card_id": "card_main",
            "start_month": "2026-01",
            "category_id": "cat_x",
        },
    )
    plan = world.create(
        "installment-plans",
        {
            "card_id": "card_main",
            "description": "TV",
            "total_installments": 3,
            "first_invoice_month": "2026-10",
            "total_amount": "300.00",
            "category_id": "cat_x",
        },
    )
    rec = world.create(
        "recurring-purchases",
        {
            "description": "Jogo",
            "estimated_amount": "50.00",
            "every": {"value": 30},
            "last_date": "2026-10-01",
            "card_id": "card_main",
            "category_id": "cat_x",
        },
    )
    rule_then = world.create(
        "rules", {"when": {"description_regex": "CINEMA"}, "then": {"category_id": "cat_x"}}
    )
    rule_when = world.create(
        "rules", {"when": {"category_id": "cat_x"}, "then": {"allocations": SHARED}}
    )
    rule_mixed = world.create(
        "rules",
        {
            "when": {"description_regex": "SHOW"},
            "then": {"category_id": "cat_x", "allocations": SHARED},
        },
    )
    assert _uncat_alert(world) is None

    r = world.delete("/api/categories/cat_x")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] == "cat_x"
    assert body["uncategorized"]["transactions"] == 1
    assert body["uncategorized"]["rules"] == 3
    assert world.get("/api/categories/cat_x").status_code == 404

    assert world.get(f"/api/transactions/{tx['id']}").json()["category_id"] is None
    assert world.get(f"/api/subscriptions/{sub['id']}").json()["category_id"] is None
    assert world.get(f"/api/installment-plans/{plan['id']}").json()["category_id"] is None
    assert world.get(f"/api/recurring-purchases/{rec['id']}").json()["category_id"] is None
    r_then = world.get(f"/api/rules/{rule_then['id']}").json()
    assert r_then["then"]["category_id"] is None
    assert r_then["enabled"] is False
    assert world.get(f"/api/rules/{rule_when['id']}").json()["enabled"] is False
    r_mixed = world.get(f"/api/rules/{rule_mixed['id']}").json()
    assert r_mixed["then"]["category_id"] is None
    assert r_mixed["enabled"] is True  # still splits

    alert = _uncat_alert(world)
    assert alert is not None
    assert alert["count"] == 4
    assert alert["items"]["transactions"] == [tx["id"]]

    uncats = world.get("/api/transactions", params={"uncategorized": True}).json()
    assert [t["id"] for t in uncats] == [tx["id"]]

    r = world.post(
        "/api/transactions/recategorize",
        {"ids": [tx["id"], sub["id"], plan["id"]], "category_id": "cat_food"},
    )
    assert r.json() == {"updated": 3}
    alert = _uncat_alert(world)
    assert alert is not None and alert["count"] == 1

    world.post("/api/transactions/recategorize", {"ids": [rec["id"]], "category_id": "cat_food"})
    assert _uncat_alert(world) is None
    assert world.get(f"/api/transactions/{tx['id']}").json()["category_id"] == "cat_food"


def test_r1_12_delete_unused_category(world: Api) -> None:
    r = world.delete("/api/categories/cat_pets")
    assert r.json() == {"deleted": "cat_pets", "uncategorized": {}}


def test_r1_12_recategorize_to_missing_category_is_rejected(world: Api) -> None:
    r = world.post("/api/transactions/recategorize", {"ids": ["x"], "category_id": "cat_ghost"})
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"


def test_r1_12_uncategorized_item_cannot_be_saved_without_category(world: Api) -> None:
    world.create("categories", {"id": "cat_x", "name": "X"})
    tx = world.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-05",
            "amount": "8.00",
            "description": "X",
            "category_id": "cat_x",
            "card_id": "card_main",
        },
    ).json()["transaction"]
    world.delete("/api/categories/cat_x")
    r = world.patch(f"/api/transactions/{tx['id']}", {"note": "sem categoria"})
    assert r.status_code == 422
    assert error_code(r) == "category_required"
    r = world.patch(f"/api/transactions/{tx['id']}", {"note": "ok", "category_id": "cat_food"})
    assert r.status_code == 200
