"""HTTP security controls (docs/13 "Controles") and the docs/12 error envelope."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from api_helpers import CSRF, Api, error_code
from fastapi.testclient import TestClient

from expense_tracker.api.app import create_app
from expense_tracker.api.security import SecurityMiddleware
from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings

# ---------------------------------------------------------------- Host (DNS rebinding)


def test_r13_host_not_loopback_is_rejected_with_invalid_host(api: Api) -> None:
    r = api.client.get("/api/health", headers={"Host": "evil.com"})
    assert r.status_code == 400
    assert error_code(r) == "invalid_host"


def test_r13_host_with_port_of_evil_domain_is_rejected(api: Api) -> None:
    r = api.client.get("/api/users", headers={"Host": "evil.com:8000"})
    assert r.status_code == 400
    assert error_code(r) == "invalid_host"


def test_r13_host_suffix_trick_is_rejected(api: Api) -> None:
    r = api.client.get("/api/users", headers={"Host": "localhost.evil.com"})
    assert r.status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:8000", "localhost", "LOCALHOST:5173"])
def test_r13_loopback_hosts_are_accepted(api: Api, host: str) -> None:
    r = api.client.get("/api/health", headers={"Host": host})
    assert r.status_code == 200


def test_r13_rejected_host_does_not_mutate(api: Api) -> None:
    r = api.client.post("/api/users", json={"name": "X"}, headers={**CSRF, "Host": "evil.com"})
    assert r.status_code == 400
    assert api.get("/api/users").json() == []


def test_r13_allowed_hosts_env_extends_the_allow_list(
    settings: Settings, clock: FixedClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", "minha-maquina.lan")
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        assert c.get("/api/health", headers={"Host": "minha-maquina.lan"}).status_code == 200
        assert c.get("/api/health", headers={"Host": "evil.com"}).status_code == 400


# ---------------------------------------------------------------- CSRF header


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "/api/users"),
        ("PUT", "/api/users/usr_x"),
        ("PATCH", "/api/transactions/tx_x"),
        ("DELETE", "/api/users/usr_x"),
        ("POST", "/api/sync/scan"),
    ],
)
def test_r13_mutation_without_x_requested_with_is_forbidden(
    api: Api, method: str, url: str
) -> None:
    r = api.client.request(method, url, json={"name": "X"})
    assert r.status_code == 403
    assert error_code(r) == "csrf_header_missing"


def test_r13_forbidden_mutation_has_no_effect(api: Api) -> None:
    api.client.post("/api/users", json={"id": "usr_x", "name": "X"})
    assert api.get("/api/users/usr_x").status_code == 404


def test_r13_reads_do_not_need_the_csrf_header(api: Api) -> None:
    assert api.client.get("/api/users").status_code == 200


# ---------------------------------------------------------------- CORS disabled


def test_r13_no_cors_header_on_preflight(api: Api) -> None:
    r = api.client.options(
        "/api/users",
        headers={
            "Origin": "http://evil.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-requested-with",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


@pytest.mark.parametrize("origin", ["http://evil.com", "http://127.0.0.1:8000", "null"])
def test_r13_no_cors_header_on_any_response(api: Api, origin: str) -> None:
    responses = [
        api.client.get("/api/health", headers={"Origin": origin}),
        api.client.get("/api/users", headers={"Origin": origin}),
        api.client.post("/api/users", json={"name": "A"}, headers={**CSRF, "Origin": origin}),
        api.client.get("/api/users/missing", headers={"Origin": origin}),
    ]
    for r in responses:
        assert not any(k.lower().startswith("access-control-") for k in r.headers), r.headers


# ---------------------------------------------------------------- path traversal


TRAVERSALS = ["../secrets.yaml", "faturas/../../secrets.yaml", "/etc/passwd", ".."]


@pytest.mark.parametrize("path", TRAVERSALS)
def test_r13_reprocess_rejects_paths_outside_inbox(api: Api, path: str) -> None:
    r = api.post("/api/sync/reprocess", {"path": path})
    assert r.status_code == 422
    assert error_code(r) == "invalid_path"


@pytest.mark.parametrize("path", TRAVERSALS)
def test_r13_profile_test_rejects_paths_outside_inbox(api: Api, path: str) -> None:
    r = api.post("/api/profiles/test", {"yaml": "id: x", "path": path})
    assert r.status_code == 422
    assert error_code(r) == "invalid_path"


@pytest.mark.parametrize(
    "url", ["/api/profiles/raw-text", "/api/sync/supersede/approve", "/api/sync/supersede/reject"]
)
def test_r13_file_actions_reject_traversal(api: Api, url: str) -> None:
    r = api.post(url, {"path": "../secrets.yaml"})
    assert r.status_code == 422
    assert error_code(r) == "invalid_path"


def test_r13_choose_owner_rejects_traversal(api: Api) -> None:
    r = api.post("/api/sync/choose-owner", {"path": "../x.pdf", "card_id": "card_x"})
    assert r.status_code == 422
    assert error_code(r) == "invalid_path"


def test_r13_symlink_pointing_outside_inbox_is_rejected(api: Api, settings: Settings) -> None:
    link = settings.inbox_dir / "faturas" / "leak.csv"
    os.symlink(settings.secrets_file, link)
    r = api.post("/api/profiles/raw-text", {"path": "faturas/leak.csv"})
    assert r.status_code == 422
    assert error_code(r) == "invalid_path"


# ---------------------------------------------------------------- error envelope (docs/12)


def test_r12_validation_errors_use_the_error_envelope(api: Api) -> None:
    r = api.post("/api/transactions", {"amount": "1.00"})
    assert r.status_code == 422
    assert error_code(r) == "validation_error"
    assert r.json()["error"]["details"]["errors"]


def test_r12_not_found_uses_the_error_envelope(api: Api) -> None:
    r = api.get("/api/cards/card_nope")
    assert r.status_code == 404
    assert error_code(r) == "not_found"


def test_health_head_and_version(api: Api) -> None:
    assert api.client.head("/api/health").status_code == 200
    assert api.get("/api/health").json()["version"]


def test_middleware_passes_non_http_scopes() -> None:
    seen: list[str] = []

    async def inner(scope, receive, send):  # type: ignore[no-untyped-def]
        seen.append(scope["type"])

    import asyncio

    mw = SecurityMiddleware(inner)
    asyncio.run(mw({"type": "lifespan"}, None, None))  # type: ignore[arg-type]
    assert seen == ["lifespan"]


# ---------------------------------------------------------------- SPA fallback


@pytest.fixture
def spa(settings: Settings, clock: FixedClock, tmp_path: Path) -> TestClient:
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>SPA</html>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    (static / "favicon.svg").write_text("<svg/>")
    (tmp_path / "outside.txt").write_text("secret")
    return TestClient(
        create_app(settings=settings, clock=clock, static_dir=static, start_background=False)
    )


def test_spa_fallback_serves_index_for_client_routes(spa: TestClient) -> None:
    with spa as c:
        r = c.get("/resumo/2026-10")
        assert r.status_code == 200
        assert "SPA" in r.text
        assert c.get("/").text == "<html>SPA</html>"
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"


def test_spa_fallback_does_not_capture_api_routes(spa: TestClient) -> None:
    with spa as c:
        r = c.get("/api/does-not-exist")
        assert r.status_code == 404
        assert "SPA" not in r.text
        assert c.get("/api/health").json()["status"] == "ok"


def test_spa_fallback_does_not_serve_files_outside_static(spa: TestClient) -> None:
    with spa as c:
        r = c.get("/%2e%2e/outside.txt")
        assert "secret" not in r.text


def test_security_headers_and_error_envelope(settings, clock, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from expense_tracker.api.app import create_app

    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        res = c.get("/api/health")
        assert res.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in res.headers["content-security-policy"]
        assert res.headers["x-content-type-options"] == "nosniff"
        missing = c.get("/api/nao-existe")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
    monkeypatch.delenv("ALLOWED_HOSTS")
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        assert c.get("/api/health").status_code == 400  # "testserver" is not allowed in prod
