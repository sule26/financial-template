"""Manual entries (R10.1, R1.11), quick-entry suggestions (R10.2), edits, rules re-application,
installment plan actions (R7) and recurring purchase actions (R12.4) through the API."""

from __future__ import annotations

from typing import Any

import pytest
from api_helpers import Api, error_code


def _entry(**over: Any) -> dict[str, Any]:
    body = {
        "purchase_date": "2026-10-05",
        "amount": "100.00",
        "description": "MERCADO BOM PRECO",
        "category_id": "cat_food",
        "card_id": "card_main",
    }
    body.update(over)
    return {k: v for k, v in body.items() if v is not None}


def _manual(api: Api, **over: Any) -> dict[str, Any]:
    r = api.post("/api/transactions", _entry(**over))
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------- R10.1 / R1.11 manual entry


def test_r1_11_manual_entry_without_category_is_rejected(world: Api) -> None:
    r = world.post("/api/transactions", _entry(category_id=None))
    assert r.status_code == 422
    assert error_code(r) == "category_required"
    assert world.get("/api/transactions").json() == []


def test_r1_11_manual_entry_with_unknown_category_is_rejected(world: Api) -> None:
    r = world.post("/api/transactions", _entry(category_id="cat_ghost"))
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"


@pytest.mark.parametrize(
    ("purchase", "month"),
    [("2026-10-02", "2026-10"), ("2026-10-03", "2026-11"), ("2026-09-03", "2026-10")],
)
def test_r10_1_credit_entry_gets_invoice_month_from_closing(
    world: Api, purchase: str, month: str
) -> None:
    """docs/07: closing 3 / due 10 — purchase on the closing day goes to the next invoice."""
    tx = _manual(world, purchase_date=purchase)["transaction"]
    assert tx["invoice_month"] == month
    assert tx["payment_method"] == "credit"
    assert tx["card_id"] == "card_main"
    assert tx["account_id"] is None
    assert tx["provisional"] is True
    assert tx["source"]["type"] == "manual"
    assert tx["amount"] == "100.00"
    assert tx["id"].startswith("tx_")


def test_r10_1_credit_entry_returns_reconciliation(world: Api) -> None:
    body = _manual(world)
    assert body["reconciliation"]["status"] == "projected"  # no invoice imported yet


@pytest.mark.parametrize("method", ["pix", "debit", "transfer", "boleto"])
def test_r10_1_checking_account_methods(world: Api, method: str) -> None:
    tx = _manual(
        world, card_id=None, account_id="acc_cc", payment_method=method, purchase_date="2026-10-11"
    )["transaction"]
    assert tx["payment_method"] == method
    assert tx["account_id"] == "acc_cc"
    assert tx["card_id"] is None
    assert tx["invoice_month"] == "2026-10"
    assert tx["provisional"] is True


def test_r10_1_benefit_entry(world: Api) -> None:
    tx = _manual(
        world,
        card_id=None,
        account_id="acc_vr",
        payment_method="benefit",
        description="RESTAURANTE",
    )["transaction"]
    assert tx["payment_method"] == "benefit"
    assert tx["account_id"] == "acc_vr"
    assert tx["provisional"] is True


def test_r10_1_cash_entry_is_definitive(world: Api) -> None:
    tx = _manual(
        world, card_id=None, account_id="acc_cash", payment_method="cash", description="FEIRA"
    )["transaction"]
    assert tx["provisional"] is False
    listed = world.get("/api/transactions", params={"provisional": False}).json()
    assert [t["id"] for t in listed] == [tx["id"]]


@pytest.mark.parametrize(
    ("account", "method"),
    [("acc_vr", "pix"), ("acc_cc", "benefit"), ("acc_cash", "debit"), ("acc_cc", "cash")],
)
def test_r10_1_method_not_allowed_on_account_type(world: Api, account: str, method: str) -> None:
    r = world.post(
        "/api/transactions", _entry(card_id=None, account_id=account, payment_method=method)
    )
    assert r.status_code == 422
    assert error_code(r) == "method_not_allowed"


def test_r10_1_credit_requires_card(world: Api) -> None:
    r = world.post("/api/transactions", _entry(card_id=None))
    assert r.status_code == 422
    assert error_code(r) == "card_required"


def test_r10_1_non_credit_requires_account(world: Api) -> None:
    r = world.post("/api/transactions", _entry(card_id=None, payment_method="pix"))
    assert r.status_code == 422
    assert error_code(r) == "account_required"


def test_r10_1_non_credit_with_card_is_rejected(world: Api) -> None:
    r = world.post("/api/transactions", _entry(account_id="acc_cc", payment_method="pix"))
    assert r.status_code == 422
    assert error_code(r) == "card_not_allowed"


@pytest.mark.parametrize(
    ("field", "value"), [("account_id", "acc_ghost"), ("card_id", "card_ghost")]
)
def test_r10_1_unknown_owner_is_rejected(world: Api, field: str, value: str) -> None:
    over = {"card_id": None, "payment_method": "pix"} if field == "account_id" else {}
    r = world.post("/api/transactions", _entry(**over, **{field: value}))
    assert r.status_code == 422


def test_r10_1_float_amount_is_rejected(world: Api) -> None:
    r = world.post("/api/transactions", _entry(amount=100.5))
    assert r.status_code == 422
    assert error_code(r) == "validation_error"


def test_r10_1_allocation_must_sum_100(world: Api) -> None:
    bad = [{"user_id": "usr_ana", "pct": "70.00"}, {"user_id": "usr_bia", "pct": "20.00"}]
    r = world.post("/api/transactions", _entry(allocations=bad))
    assert r.status_code == 422


def test_r10_1_allocation_with_unknown_user_is_rejected(world: Api) -> None:
    r = world.post(
        "/api/transactions", _entry(allocations=[{"user_id": "usr_ghost", "pct": "100.00"}])
    )
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"


def test_r10_1_explicit_allocation_is_kept_as_manual(world: Api) -> None:
    alloc = [{"user_id": "usr_bia", "pct": "100.00"}]
    tx = _manual(world, allocations=alloc)["transaction"]
    assert tx["allocations"] == alloc
    assert tx["allocation_origin"] == "manual"


def test_r10_1_unknown_field_is_rejected(world: Api) -> None:
    r = world.post("/api/transactions", {**_entry(), "fingerprint": "x"})
    assert r.status_code == 422


def test_r10_1_installments_create_a_plan(world: Api) -> None:
    body = _manual(world, installments=3, amount="300.00", purchase_date="2026-10-05")
    assert "transaction" not in body
    plan = body["plan"]
    assert plan["total_installments"] == 3
    assert plan["total_amount"] == "300.00"
    assert plan["first_invoice_month"] == "2026-11"
    assert plan["category_id"] == "cat_food"
    assert world.get(f"/api/installment-plans/{plan['id']}").json() == plan
    assert world.get("/api/transactions").json() == []
    proj = {m["month"]: m["total"] for m in world.get("/api/reports/projection").json()["months"]}
    assert proj["2026-11"] == "100.00"
    assert proj["2027-01"] == "100.00"
    assert proj["2027-02"] == "0.00"


def test_r10_1_installments_only_on_credit(world: Api) -> None:
    r = world.post(
        "/api/transactions",
        _entry(card_id=None, account_id="acc_cc", payment_method="pix", installments=2),
    )
    assert r.status_code == 422
    assert error_code(r) == "installments_credit_only"


@pytest.mark.parametrize("n", [0, 121])
def test_r10_1_installments_range(world: Api, n: int) -> None:
    assert world.post("/api/transactions", _entry(installments=n)).status_code == 422


def test_r12_manual_entry_linked_to_recurring_reanchors_it(world: Api) -> None:
    rec = world.create(
        "recurring-purchases",
        {
            "description": "Ração",
            "estimated_amount": "180.00",
            "every": {"value": 45},
            "last_date": "2026-08-01",
            "card_id": "card_main",
            "category_id": "cat_pets",
        },
    )
    tx = _manual(
        world,
        description="PETZ RACAO",
        category_id="cat_pets",
        purchase_date="2026-10-10",
        recurring_purchase_id=rec["id"],
    )["transaction"]
    assert tx["links"]["recurring_purchase_id"] == rec["id"]
    after = world.get(f"/api/recurring-purchases/{rec['id']}").json()
    assert after["last_date"] == "2026-10-10"


def test_r12_manual_entry_with_unknown_recurring_is_rejected(world: Api) -> None:
    r = world.post("/api/transactions", _entry(recurring_purchase_id="rec_ghost"))
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"


def test_r1_delete_recurring_linked_by_transaction_is_conflict(world: Api) -> None:
    rec = world.create(
        "recurring-purchases",
        {
            "description": "Ração",
            "estimated_amount": "180.00",
            "every": {"value": 45},
            "last_date": "2026-08-01",
            "card_id": "card_main",
            "category_id": "cat_pets",
        },
    )
    _manual(world, recurring_purchase_id=rec["id"], purchase_date="2026-10-10")
    r = world.delete(f"/api/recurring-purchases/{rec['id']}")
    assert r.status_code == 409


# ---------------------------------------------------------------- list / get / filters


def test_transactions_list_filters(world: Api) -> None:
    a = _manual(world, description="PADARIA SOL", purchase_date="2026-10-01")["transaction"]
    b = _manual(world, description="FARMACIA", purchase_date="2026-10-04")["transaction"]
    c = _manual(
        world,
        card_id=None,
        account_id="acc_cc",
        payment_method="pix",
        description="PIX ALUGUEL",
        purchase_date="2026-10-06",
    )["transaction"]
    ids = lambda **p: [t["id"] for t in world.get("/api/transactions", params=p).json()]  # noqa: E731
    assert ids() == [c["id"], b["id"], a["id"]]  # newest first
    assert ids(month="2026-10") == [c["id"], a["id"]]
    assert ids(card_id="card_main") == [b["id"], a["id"]]
    assert ids(account_id="acc_cc") == [c["id"]]
    assert ids(payment_method="pix") == [c["id"]]
    assert ids(q="padaria") == [a["id"]]
    assert ids(provisional=True) == [c["id"], b["id"], a["id"]]
    assert ids(uncategorized=True) == []
    assert world.get("/api/transactions", params={"month": "2026-13"}).status_code == 422


def test_transaction_get_not_found(world: Api) -> None:
    r = world.get("/api/transactions/tx_nope")
    assert r.status_code == 404
    assert error_code(r) == "not_found"
    assert world.patch("/api/transactions/tx_nope", {"note": "x"}).status_code == 404
    assert world.delete("/api/transactions/tx_nope").status_code == 404


# ---------------------------------------------------------------- R10.2 suggestions


def test_r10_2_suggest_category_by_rule(world: Api) -> None:
    rule = world.create(
        "rules", {"when": {"description_regex": "IFOOD"}, "then": {"category_id": "cat_food"}}
    )
    s = world.get(
        "/api/transactions/suggest",
        params={"description": "IFOOD *RESTAURANTE", "card_id": "card_main", "amount": "45.90"},
    ).json()
    assert s["category_id"] == "cat_food"
    assert s["category_origin"] == f"rule:{rule['id']}"


def test_r10_2_suggest_category_by_history(world: Api) -> None:
    _manual(world, description="PETZ RACAO", category_id="cat_pets", purchase_date="2026-09-01")
    s = world.get(
        "/api/transactions/suggest", params={"description": "petz racao", "card_id": "card_main"}
    ).json()
    assert s["category_id"] == "cat_pets"
    assert s["category_origin"] == "history"


def test_r10_2_history_uses_the_most_recent_category(world: Api) -> None:
    _manual(world, description="PETZ", category_id="cat_pets", purchase_date="2026-08-01")
    _manual(world, description="PETZ", category_id="cat_food", purchase_date="2026-09-01")
    s = world.get(
        "/api/transactions/suggest", params={"description": "PETZ", "card_id": "card_main"}
    ).json()
    assert s["category_id"] == "cat_food"


def test_r10_2_rule_beats_history(world: Api) -> None:
    _manual(world, description="PETZ", category_id="cat_food", purchase_date="2026-09-01")
    world.create(
        "rules", {"when": {"description_regex": "PETZ"}, "then": {"category_id": "cat_pets"}}
    )
    s = world.get(
        "/api/transactions/suggest", params={"description": "PETZ", "card_id": "card_main"}
    ).json()
    assert s["category_id"] == "cat_pets"


def test_r10_2_suggest_allocation_from_owner_and_rule(world: Api) -> None:
    s = world.get(
        "/api/transactions/suggest", params={"description": "QUALQUER", "card_id": "card_main"}
    ).json()
    assert s["category_id"] is None
    pcts = {a["user_id"]: a["pct"] for a in s["allocations"]}
    assert pcts == {"usr_ana": "50.00", "usr_bia": "50.00"}
    world.create(
        "split-profiles",
        {
            "id": "split_c",
            "name": "Casal",
            "members": ["usr_ana", "usr_bia"],
            "history": [
                {
                    "from_month": "2026-01",
                    "shares": [
                        {"user_id": "usr_ana", "pct": "70.00"},
                        {"user_id": "usr_bia", "pct": "30.00"},
                    ],
                }
            ],
        },
    )
    rule = world.create(
        "rules",
        {
            "when": {"description_regex": "ALUGUEL"},
            "then": {"allocations": {"split_id": "split_c"}},
        },
    )
    s = world.get(
        "/api/transactions/suggest",
        params={"description": "ALUGUEL", "payment_method": "pix", "account_id": "acc_cc"},
    ).json()
    assert s["allocations"] == {"split_id": "split_c"}
    assert s["allocation_origin"] == f"rule:{rule['id']}"


def test_r10_2_autocomplete_known_descriptions(world: Api) -> None:
    _manual(world, description="PETZ RACAO", category_id="cat_pets", purchase_date="2026-09-01")
    _manual(world, description="PETSHOP BICHO", category_id="cat_pets", purchase_date="2026-09-05")
    _manual(world, description="PADARIA", purchase_date="2026-09-06")
    s = world.get(
        "/api/transactions/suggest", params={"description": "pet", "card_id": "card_main"}
    ).json()
    assert s["descriptions"] == ["PETSHOP BICHO", "PETZ RACAO"]


def test_r10_2_autocomplete_is_limited(world: Api) -> None:
    for i in range(10):
        _manual(world, description=f"LOJA {i}", purchase_date=f"2026-09-{i + 10}")
    s = world.get(
        "/api/transactions/suggest", params={"description": "loja", "card_id": "card_main"}
    ).json()
    assert len(s["descriptions"]) == 8
    assert s["descriptions"][0] == "LOJA 9"  # most recent first


def test_r10_2_suggest_validates_input(world: Api) -> None:
    r = world.get(
        "/api/transactions/suggest",
        params={"description": "X", "card_id": "card_main", "amount": "abc"},
    )
    assert r.status_code == 422
    assert error_code(r) == "invalid_amount"
    r = world.get("/api/transactions/suggest", params={"description": "X"})
    assert r.status_code == 422
    assert error_code(r) == "card_required"
    r = world.get(
        "/api/transactions/suggest",
        params={"description": "X", "payment_method": "pix", "account_id": "acc_ghost"},
    )
    assert r.status_code == 422
    assert error_code(r) == "reference_not_found"


# ---------------------------------------------------------------- edits of manual entries


def test_manual_entry_can_be_fully_edited(world: Api) -> None:
    tx = _manual(world)["transaction"]
    r = world.patch(
        f"/api/transactions/{tx['id']}",
        {
            "amount": "120.00",
            "description": "MERCADO X",
            "purchase_date": "2026-10-03",
            "note": "compra do mês",
            "category_id": "cat_pets",
            "allocations": [{"user_id": "usr_ana", "pct": "100.00"}],
            "provisional": False,
        },
    )
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["amount"] == "120.00"
    assert new["invoice_month"] == "2026-11"  # recomputed from the new date
    assert new["allocation_origin"] == "manual"
    assert new["provisional"] is False
    assert world.get(f"/api/transactions/{tx['id']}").json() == new


def test_manual_account_entry_date_change_recomputes_month(world: Api) -> None:
    tx = _manual(world, card_id=None, account_id="acc_cc", payment_method="pix")["transaction"]
    new = world.patch(f"/api/transactions/{tx['id']}", {"purchase_date": "2026-09-30"}).json()
    assert new["invoice_month"] == "2026-09"


def test_patch_rejects_float_and_unknown_refs(world: Api) -> None:
    tx = _manual(world)["transaction"]
    url = f"/api/transactions/{tx['id']}"
    assert world.patch(url, {"amount": 1.5}).status_code == 422
    r = world.patch(url, {"category_id": "cat_ghost"})
    assert error_code(r) == "reference_not_found"
    r = world.patch(url, {"allocations": [{"user_id": "usr_ghost", "pct": "100.00"}]})
    assert error_code(r) == "reference_not_found"
    r = world.patch(url, {"category_id": None})
    assert error_code(r) == "category_required"
    assert world.patch(url, {"source": {"type": "import"}}).status_code == 422


def test_transfer_kind_needs_no_category(world: Api) -> None:
    tx = _manual(
        world,
        card_id=None,
        account_id="acc_cc",
        payment_method="transfer",
        kind="transfer",
        category_id=None,
        description="TED POUPANCA",
    )["transaction"]
    assert tx["category_id"] is None
    alerts = world.get("/api/alerts").json()
    assert not any(a["type"] == "uncategorized" for a in alerts)


def test_manual_entry_can_be_deleted(world: Api) -> None:
    tx = _manual(world)["transaction"]
    assert world.delete(f"/api/transactions/{tx['id']}").json() == {"deleted": tx["id"]}
    assert world.get(f"/api/transactions/{tx['id']}").status_code == 404


# ---------------------------------------------------------------- reapply rules (docs/08)


def test_reapply_rules_preview_then_apply(world: Api) -> None:
    world.create("categories", {"id": "cat_transp", "name": "Transporte"})
    tx = _manual(world, description="UBER TRIP")["transaction"]
    keep = _manual(
        world, description="UBER EATS", allocations=[{"user_id": "usr_ana", "pct": "100.00"}]
    )["transaction"]
    world.create(
        "rules",
        {
            "id": "rule_uber",
            "when": {"description_regex": "UBER"},
            "then": {"category_id": "cat_transp"},
        },
    )

    preview = world.post("/api/transactions/reapply-rules").json()
    assert preview["applied"] is False
    assert preview["count"] == 1
    assert [c["id"] for c in preview["changes"]] == [tx["id"]]
    assert preview["changes"][0]["category_id"] == "cat_transp"
    assert world.get(f"/api/transactions/{tx['id']}").json()["category_id"] == "cat_food"

    applied = world.post("/api/transactions/reapply-rules?apply=true").json()
    assert applied["applied"] is True and applied["count"] == 1
    assert world.get(f"/api/transactions/{tx['id']}").json()["category_id"] == "cat_transp"
    # manual allocation edits are never overwritten
    assert world.get(f"/api/transactions/{keep['id']}").json()["category_id"] == "cat_food"
    assert world.post("/api/transactions/reapply-rules").json()["count"] == 0


def test_reapply_rules_applies_rule_allocation(world: Api) -> None:
    tx = _manual(
        world, description="ALUGUEL", card_id=None, account_id="acc_cc", payment_method="pix"
    )["transaction"]
    only_bia = [{"user_id": "usr_bia", "pct": "100.00"}]
    world.create(
        "rules",
        {
            "id": "rule_a",
            "when": {"description_regex": "ALUGUEL"},
            "then": {"allocations": only_bia},
        },
    )
    out = world.post("/api/transactions/reapply-rules?apply=true").json()
    assert out["changes"][0]["allocation_origin"] == "rule:rule_a"
    new = world.get(f"/api/transactions/{tx['id']}").json()
    assert new["allocations"] == only_bia


# ---------------------------------------------------------------- R7 installment plans


@pytest.fixture
def plan(world: Api) -> dict[str, Any]:
    """10 x 100.00 starting 2026-10; today 2026-10-12 → H(card_main) = 2026-11."""
    return world.create(
        "installment-plans",
        {
            "id": "plan_tv",
            "card_id": "card_main",
            "description": "TV",
            "total_installments": 10,
            "first_invoice_month": "2026-10",
            "total_amount": "1000.00",
            "category_id": "cat_food",
        },
    )


def test_r7_1_anticipate_defaults_to_next_open_invoice(world: Api, plan: dict[str, Any]) -> None:
    r = world.post("/api/installment-plans/plan_tv/anticipate", {})
    assert r.status_code == 200, r.text
    ant = r.json()["anticipation"]
    assert ant["target_month"] == "2026-11"
    assert ant["from_n"] == 2
    proj = {m["month"]: m["total"] for m in world.get("/api/reports/projection").json()["months"]}
    assert proj["2026-10"] == "100.00"
    assert proj["2026-11"] == "900.00"
    assert proj["2026-12"] == "0.00"


def test_r7_2_anticipate_with_bank_discount(world: Api, plan: dict[str, Any]) -> None:
    r = world.post(
        "/api/installment-plans/plan_tv/anticipate",
        {"from_n": 5, "target_month": "2027-02", "amount": "500.00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["anticipation"] == {
        "from_n": 5,
        "target_month": "2027-02",
        "amount": "500.00",
        "linked_fingerprints": [],
    }
    proj = {m["month"]: m["total"] for m in world.get("/api/reports/projection").json()["months"]}
    assert proj["2027-02"] == "500.00"
    assert proj["2027-03"] == "0.00"


def test_r7_1_anticipate_to_past_month_is_rejected(world: Api, plan: dict[str, Any]) -> None:
    r = world.post("/api/installment-plans/plan_tv/anticipate", {"target_month": "2026-10"})
    assert r.status_code == 422
    assert error_code(r) == "plan_error"
    assert world.get("/api/installment-plans/plan_tv").json()["anticipation"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"from_n": 99},
        {"from_n": 1, "target_month": "2026-12"},
        {"amount": "-1.00"},
        {"amount": 10.5},
    ],
)
def test_r7_anticipate_invalid(world: Api, plan: dict[str, Any], body: dict[str, Any]) -> None:
    r = world.post("/api/installment-plans/plan_tv/anticipate", body)
    assert r.status_code == 422


def test_r7_4_undo_anticipation_restores_schedule(world: Api, plan: dict[str, Any]) -> None:
    world.post("/api/installment-plans/plan_tv/anticipate", {})
    r = world.delete("/api/installment-plans/plan_tv/anticipation")
    assert r.status_code == 200
    assert r.json()["anticipation"] is None
    proj = {m["month"]: m["total"] for m in world.get("/api/reports/projection").json()["months"]}
    assert proj["2026-12"] == "100.00"
    r = world.delete("/api/installment-plans/plan_tv/anticipation")
    assert r.status_code == 422
    assert error_code(r) == "plan_error"


def test_r8_7_cancel_plan(world: Api, plan: dict[str, Any]) -> None:
    r = world.post("/api/installment-plans/plan_tv/cancel", {"from_n": 4})
    assert r.status_code == 200
    assert r.json()["status_override"] == {"status": "cancelled", "from_n": 4}
    proj = {m["month"]: m["total"] for m in world.get("/api/reports/projection").json()["months"]}
    assert proj["2026-12"] == "100.00"
    assert proj["2027-01"] == "0.00"
    r = world.post("/api/installment-plans/plan_tv/anticipate", {})
    assert error_code(r) == "plan_error"
    assert world.post("/api/installment-plans/plan_tv/cancel", {"from_n": 11}).status_code == 422


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("POST", "/api/installment-plans/plan_ghost/anticipate", {}),
        ("DELETE", "/api/installment-plans/plan_ghost/anticipation", None),
        ("POST", "/api/installment-plans/plan_ghost/cancel", {"from_n": 1}),
    ],
)
def test_r7_plan_actions_not_found(world: Api, method: str, url: str, body: Any) -> None:
    r = world.client.request(method, url, json=body, headers={"X-Requested-With": "t"})
    assert r.status_code == 404
    assert error_code(r) == "not_found"


def test_r7_plan_statuses(world: Api, plan: dict[str, Any]) -> None:
    world.create(
        "installment-plans",
        {
            "id": "plan_old",
            "card_id": "card_main",
            "description": "Velho",
            "total_installments": 2,
            "first_invoice_month": "2026-01",
            "total_amount": "20.00",
            "category_id": "cat_food",
        },
    )
    statuses = world.get("/api/installment-plans-status").json()
    assert set(statuses) == {"plan_tv", "plan_old"}
    assert statuses["plan_tv"] != statuses["plan_old"]


# ---------------------------------------------------------------- R12.4 recurring actions


@pytest.fixture
def rec(world: Api) -> dict[str, Any]:
    """Every 45 days from 2026-08-01 → planned 2026-09-15, overdue on 2026-10-12."""
    return world.create(
        "recurring-purchases",
        {
            "id": "rec_racao",
            "description": "Ração",
            "estimated_amount": "180.00",
            "every": {"value": 45},
            "last_date": "2026-08-01",
            "card_id": "card_main",
            "category_id": "cat_pets",
        },
    )


def _overdue(api: Api) -> list[dict[str, Any]]:
    return [a for a in api.get("/api/alerts").json() if a["type"] == "recurring_overdue"]


def test_r12_4_overdue_recurring_raises_alert(world: Api, rec: dict[str, Any]) -> None:
    alerts = _overdue(world)
    assert len(alerts) == 1
    assert alerts[0]["recurring_id"] == "rec_racao"
    assert alerts[0]["planned_date"] == "2026-09-15"


def test_r12_4_postpone(world: Api, rec: dict[str, Any]) -> None:
    r = world.post(
        "/api/recurring-purchases/rec_racao/action", {"action": "postpone", "date": "2026-10-20"}
    )
    assert r.status_code == 200
    assert r.json()["next_date"] == "2026-10-20"
    assert world.get("/api/recurring-purchases/rec_racao").json()["next_date"] == "2026-10-20"
    assert _overdue(world) == []


def test_r12_4_skip(world: Api, rec: dict[str, Any]) -> None:
    r = world.post(
        "/api/recurring-purchases/rec_racao/action", {"action": "skip", "date": "2026-09-15"}
    )
    assert r.status_code == 200
    assert r.json()["skipped_dates"] == ["2026-09-15"]
    assert all(a["planned_date"] != "2026-09-15" for a in _overdue(world))


def test_r12_4_end(world: Api, rec: dict[str, Any]) -> None:
    r = world.post("/api/recurring-purchases/rec_racao/action", {"action": "end"})
    # R14.11: "desativar" keeps the history as a pause from the first missed purchase on
    assert r.json()["active"] is True
    assert r.json()["pauses"] == [{"from_month": "2026-09", "until_month": None}]
    assert _overdue(world) == []


def test_r14_10_r14_11_resume_closes_the_pause(world: Api, rec: dict[str, Any]) -> None:
    world.post("/api/recurring-purchases/rec_racao/action", {"action": "end"})
    r = world.post(
        "/api/recurring-purchases/rec_racao/action", {"action": "resume", "date": "2026-10-20"}
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["active"], body["next_date"]) == (True, "2026-10-20")
    assert body["pauses"] == [{"from_month": "2026-09", "until_month": "2026-09"}]
    assert _overdue(world) == []  # next purchase in the future: nothing overdue
    # desativar again this month and come back this month: that pause is dropped
    world.post("/api/recurring-purchases/rec_racao/action", {"action": "end"})
    r = world.post("/api/recurring-purchases/rec_racao/action", {"action": "resume"})
    assert r.json()["pauses"] == [{"from_month": "2026-09", "until_month": "2026-09"}]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"action": "postpone"}, "date_required"),
        ({"action": "skip"}, "date_required"),
        ({"action": "explode"}, "invalid_action"),
    ],
)
def test_r12_4_invalid_actions(
    world: Api, rec: dict[str, Any], body: dict[str, Any], code: str
) -> None:
    r = world.post("/api/recurring-purchases/rec_racao/action", body)
    assert r.status_code == 422
    assert error_code(r) == code


def test_r12_4_action_on_unknown_recurring(world: Api) -> None:
    r = world.post("/api/recurring-purchases/rec_ghost/action", {"action": "end"})
    assert r.status_code == 404
