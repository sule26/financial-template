"""Application factory wiring: background service lifecycle, startup hooks, extra routers and
an injected repository."""

from __future__ import annotations

from typing import Any

from api_helpers import CSRF
from fastapi import APIRouter
from fastapi.testclient import TestClient

from expense_tracker.api.app import create_app
from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings
from expense_tracker.storage import Repository


class _Task:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


def test_background_service_and_startup_hooks_start_and_stop(
    settings: Settings, clock: FixedClock
) -> None:
    task = _Task()
    calls: list[bool] = []

    def hook(app: Any, start_background: bool) -> _Task:
        calls.append(start_background)
        return task

    def silent_hook(app: Any, start_background: bool) -> None:
        calls.append(start_background)

    extra = APIRouter()

    @extra.get("/api/extra")
    def _extra() -> dict[str, str]:
        return {"ok": "yes"}

    app = create_app(
        settings=settings,
        clock=clock,
        start_background=True,
        on_startup=[hook, silent_hook],
        extra_routers=[extra],
    )
    with TestClient(app) as c:
        assert c.get("/api/extra").json() == {"ok": "yes"}
        r = c.post("/api/sync/scan", headers=CSRF)
        assert r.status_code == 202
        assert r.json()["kind"] == "scan"
    assert calls == [True, True]
    assert task.stopped is True


def test_injected_repository_is_not_closed_by_the_app(
    settings: Settings, clock: FixedClock
) -> None:
    repo = Repository(settings.data_dir, settings.backups_keep).open()
    try:
        app = create_app(settings=settings, clock=clock, repo=repo, start_background=False)
        with TestClient(app) as c:
            r = c.post("/api/users", json={"id": "usr_x", "name": "X"}, headers=CSRF)
            assert r.status_code == 201
        # still usable after the app shut down
        assert repo.get("users", "usr_x") is not None
    finally:
        repo.close()


def test_data_persists_across_app_restarts(settings: Settings, clock: FixedClock) -> None:
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        c.post("/api/categories", json={"id": "cat_a", "name": "A"}, headers=CSRF)
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        assert c.get("/api/categories/cat_a").json()["name"] == "A"


def test_openapi_is_served_under_api(settings: Settings, clock: FixedClock) -> None:
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        spec = c.get("/api/openapi.json").json()
        assert "/api/transactions" in spec["paths"]
        assert "/api/users/{item_id}" in spec["paths"]
