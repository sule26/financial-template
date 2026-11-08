"""R14.17 (bug): a manual entry in a future month must not disappear from lists and reports."""

from __future__ import annotations

from typing import Any

import pytest
from api_helpers import Api


def _manual(world: Api, **over: Any) -> dict[str, Any]:
    body = {
        "purchase_date": "2027-01-15",
        "amount": "90.00",
        "description": "DENTISTA",
        "category_id": "cat_food",
        "card_id": "card_main",
        **over,
    }
    r = world.post("/api/transactions", {k: v for k, v in body.items() if v is not None})
    assert r.status_code == 201, r.text
    return r.json()["transaction"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "target",
    [
        {"card_id": "card_main"},
        {"card_id": None, "account_id": "acc_cc", "payment_method": "pix"},
    ],
)
def test_r14_17_future_manual_entry_stays_everywhere(world: Api, target: dict[str, Any]) -> None:
    tx = _manual(world, **target)
    month = tx["invoice_month"]
    listed = world.get("/api/transactions", params={"month": month}).json()
    assert [t["id"] for t in listed] == [tx["id"]]
    items = world.get("/api/reports/month-items", params={"month": month}).json()
    assert [i["ref_id"] for i in items] == [tx["id"]]
    summary = world.get("/api/reports/summary", params={"month": month}).json()
    assert summary["total"] == "90.00"
