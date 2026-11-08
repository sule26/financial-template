"""Fixtures for API/service tests: a TestClient with the CSRF header and a seeded catalog."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from expense_tracker.api.app import create_app
from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings

CSRF = {"X-Requested-With": "pytest"}
EXAMPLES = Path(__file__).resolve().parents[3] / "profiles" / "examples"


@dataclass
class Api:
    """Thin wrapper that always sends the CSRF header on mutations."""

    client: TestClient

    def get(self, url: str, **kw: Any) -> Any:
        return self.client.get(url, **kw)

    def post(self, url: str, json: Any = None, **kw: Any) -> Any:
        return self.client.post(url, json=json, headers=CSRF, **kw)

    def put(self, url: str, json: Any = None) -> Any:
        return self.client.put(url, json=json, headers=CSRF)

    def patch(self, url: str, json: Any = None) -> Any:
        return self.client.patch(url, json=json, headers=CSRF)

    def delete(self, url: str) -> Any:
        return self.client.delete(url, headers=CSRF)

    def create(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = self.post(f"/api/{path}", body)
        assert r.status_code == 201, r.text
        return r.json()  # type: ignore[no-any-return]

    @property
    def repo(self) -> Any:
        return self.client.app.state.ctx.repo  # type: ignore[attr-defined]


def error_code(response: Any) -> str:
    """Assert the docs/12 error envelope and return its code."""
    body = response.json()
    assert set(body) == {"error"}, body
    assert {"code", "message", "details"} <= set(body["error"]), body
    return body["error"]["code"]  # type: ignore[no-any-return]


@pytest.fixture
def api(settings: Settings, clock: FixedClock) -> Iterator[Api]:
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        yield Api(c)


def seed_world(api: Api) -> None:
    """Two users, a shared checking account, benefit and cash accounts, a main card
    (closing 3 / due 10, inheriting the account owners) and two categories."""
    api.create("users", {"id": "usr_ana", "name": "Ana"})
    api.create("users", {"id": "usr_bia", "name": "Bia"})
    shared = [{"user_id": "usr_ana", "pct": "50.00"}, {"user_id": "usr_bia", "pct": "50.00"}]
    api.create(
        "accounts",
        {
            "id": "acc_cc",
            "name": "Conta conjunta",
            "type": "checking",
            "owners": shared,
            "responsible_user_id": "usr_ana",
        },
    )
    only_ana = [{"user_id": "usr_ana", "pct": "100.00"}]
    api.create(
        "accounts",
        {
            "id": "acc_vr",
            "name": "VR",
            "type": "benefit",
            "owners": only_ana,
            "responsible_user_id": "usr_ana",
        },
    )
    api.create(
        "accounts",
        {
            "id": "acc_cash",
            "name": "Carteira",
            "type": "cash",
            "owners": only_ana,
            "responsible_user_id": "usr_ana",
        },
    )
    api.create(
        "cards",
        {
            "id": "card_main",
            "name": "Cartão principal",
            "account_id": "acc_cc",
            "last_digits": ["1234"],
            "billing_history": [{"from_month": "2026-01", "closing_day": 3, "due_day": 10}],
        },
    )
    api.create("categories", {"id": "cat_food", "name": "Alimentação"})
    api.create("categories", {"id": "cat_pets", "name": "Pets"})


@pytest.fixture
def world(api: Api) -> Api:
    seed_world(api)
    return api
