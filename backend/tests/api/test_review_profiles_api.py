"""Review flow, sync actions and bank profiles through the API (docs/05, 06, 09; R4.3, R1.11)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from api_helpers import EXAMPLES, Api, error_code

from expense_tracker.config import Settings
from fixtures.files import (
    OPEN_INVOICE_CSV_PROFILE,
    Line,
    inter_invoice,
    open_invoice_csv,
    write,
)

INVOICE = "faturas/inter-2026-10.pdf"
INTER_YAML = (EXAMPLES / "inter-fatura.yaml").read_text("utf-8")


def _lines() -> list[Line]:
    return [
        Line(5, 9, 2026, "IFOOD RESTAURANTE", "45.90"),
        Line(8, 9, 2026, "POSTO SHELL", "200.00", card="1234"),
        Line(9, 9, 2026, "PAGAMENTO ON LINE", "-300.00"),
    ]


@pytest.fixture
def inbox(world: Api, settings: Settings) -> Api:
    """Inter example profile installed, main + additional card, one invoice in the inbox."""
    shutil.copy(EXAMPLES / "inter-fatura.yaml", settings.profiles_dir / "inter-fatura.yaml")
    world.create(
        "cards",
        {
            "id": "card_add",
            "name": "Adicional",
            "parent_card_id": "card_main",
            "last_digits": ["5678"],
        },
    )
    write(settings.inbox_dir / INVOICE, inter_invoice(_lines()))
    return world


@pytest.fixture
def scanned(inbox: Api) -> Api:
    r = inbox.post("/api/sync/scan")
    assert r.status_code == 202, r.text
    return inbox


def _review_lines(api: Api) -> dict[str, dict[str, Any]]:
    files = api.get("/api/review").json()
    return {ln["description"]: ln for f in files for ln in f["lines"]}


@pytest.fixture
def confirmed(scanned: Api) -> Api:
    lines = _review_lines(scanned)
    for desc in ("IFOOD RESTAURANTE", "POSTO SHELL"):
        r = scanned.patch(f"/api/review/lines/{lines[desc]['id']}", {"category_id": "cat_food"})
        assert r.status_code == 200, r.text
    r = scanned.post("/api/review/confirm", {"path": INVOICE})
    assert r.status_code == 200, r.text
    return scanned


# ---------------------------------------------------------------- scan → review → confirm


def test_scan_reports_new_file_and_job(scanned: Api) -> None:
    status = scanned.get("/api/sync/status").json()
    assert status["last_scan"] == "2026-10-12T10:00:00-03:00"
    assert status["last_report"]["new"] == [INVOICE]
    [job] = status["jobs"]
    assert job["kind"] == "scan" and job["status"] == "done"
    assert scanned.get(f"/api/sync/jobs/{job['id']}").json()["id"] == job["id"]
    r = scanned.get("/api/sync/jobs/job_ghost")
    assert r.status_code == 404
    [f] = status["files"]
    assert f["path"] == INVOICE
    assert f["status"] == "pending_review"
    assert f["label"]


def test_review_lists_staged_lines_of_pending_file(scanned: Api) -> None:
    [f] = scanned.get("/api/review").json()
    assert f["file"]["path"] == INVOICE
    assert f["file"]["card_id"] == "card_main"
    assert f["file"]["invoice_month"] == "2026-10"
    assert f["file"]["total"] == "245.90"
    # R14.8: the invoice's "PAGAMENTO ON LINE" (payment seen from the card) is not staged
    assert f["count"] == 2
    assert [ln["source"]["line"] for ln in f["lines"]] == sorted(
        ln["source"]["line"] for ln in f["lines"]
    )
    by_desc = {ln["description"]: ln for ln in f["lines"]}
    assert by_desc["IFOOD RESTAURANTE"]["card_id"] == "card_add"
    assert by_desc["POSTO SHELL"]["card_id"] == "card_main"
    assert "PAGAMENTO ON LINE" not in by_desc
    assert by_desc["IFOOD RESTAURANTE"]["amount"] == "45.90"
    # nothing is a transaction until confirmed
    assert scanned.get("/api/transactions").json() == []


def test_r1_11_review_line_without_category_cannot_be_confirmed(scanned: Api) -> None:
    lines = _review_lines(scanned)
    r = scanned.post("/api/review/confirm", {"ids": [lines["IFOOD RESTAURANTE"]["id"]]})
    assert r.status_code == 422
    assert error_code(r) == "cannot_confirm"
    assert scanned.get("/api/transactions").json() == []


def test_review_patch_then_confirm_by_ids_and_by_path(scanned: Api) -> None:
    lines = _review_lines(scanned)
    ifood = lines["IFOOD RESTAURANTE"]
    only_bia = [{"user_id": "usr_bia", "pct": "100.00"}]
    r = scanned.patch(
        f"/api/review/lines/{ifood['id']}",
        {"category_id": "cat_food", "allocations": only_bia, "note": "jantar"},
    )
    assert r.status_code == 200, r.text
    after = _review_lines(scanned)["IFOOD RESTAURANTE"]
    assert after["category_id"] == "cat_food"
    assert after["allocations"] == only_bia
    assert after["allocation_origin"] == "manual"
    assert "category_missing" not in after["review"]["warnings"]

    r = scanned.post("/api/review/confirm", {"ids": [ifood["id"]]})
    assert r.status_code == 200, r.text
    txs = scanned.get("/api/transactions").json()
    assert [t["description"] for t in txs] == ["IFOOD RESTAURANTE"]
    assert txs[0]["source"]["type"] == "import"
    assert txs[0]["note"] == "jantar"
    assert set(_review_lines(scanned)) == {"POSTO SHELL"}

    posto = _review_lines(scanned)["POSTO SHELL"]
    scanned.patch(f"/api/review/lines/{posto['id']}", {"category_id": "cat_food"})
    r = scanned.post("/api/review/confirm", {"path": INVOICE})
    assert r.status_code == 200, r.text
    assert scanned.get("/api/review").json() == []
    descs = {t["description"] for t in scanned.get("/api/transactions").json()}
    assert descs == {"IFOOD RESTAURANTE", "POSTO SHELL"}
    [f] = scanned.get("/api/sync/status").json()["files"]
    assert f["status"] != "pending_review"


def test_review_patch_errors(scanned: Api) -> None:
    line = _review_lines(scanned)["IFOOD RESTAURANTE"]
    url = f"/api/review/lines/{line['id']}"
    r = scanned.patch(url, {"category_id": "cat_ghost"})
    assert r.status_code == 422 and error_code(r) == "reference_not_found"
    r = scanned.patch(url, {"allocations": [{"user_id": "usr_ghost", "pct": "100.00"}]})
    assert r.status_code == 422 and error_code(r) == "reference_not_found"
    r = scanned.patch(url, {"allocations": [{"user_id": "usr_ana", "pct": "99.00"}]})
    assert r.status_code == 422
    r = scanned.patch(url, {"choose": {"type": "choose_plan", "target_id": "x"}})
    assert r.status_code == 422 and error_code(r) == "invalid_choice"
    r = scanned.patch(url, {"unknown": 1})
    assert r.status_code == 422
    r = scanned.patch("/api/review/lines/tx_ghost", {"category_id": "cat_food"})
    assert r.status_code == 422 and error_code(r) == "not_found"


def test_review_change_kind_on_a_card_line(scanned: Api) -> None:
    line = _review_lines(scanned)["POSTO SHELL"]
    url = f"/api/review/lines/{line['id']}"
    r = scanned.patch(url, {"kind": "refund", "category_id": "cat_food"})
    assert r.status_code == 200
    assert _review_lines(scanned)["POSTO SHELL"]["kind"] == "refund"


def test_r14_8_card_line_cannot_become_income_or_transfer(scanned: Api) -> None:
    line = _review_lines(scanned)["POSTO SHELL"]
    r = scanned.patch(f"/api/review/lines/{line['id']}", {"kind": "transfer"})
    assert (r.status_code, error_code(r)) == (422, "invalid_kind")


def test_review_patch_invalid_kind_is_422(scanned: Api) -> None:
    line = _review_lines(scanned)["IFOOD RESTAURANTE"]
    r = scanned.patch(f"/api/review/lines/{line['id']}", {"kind": "nonsense"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({}, 422, "nothing_to_confirm"),
        ({"ids": []}, 422, "nothing_to_confirm"),
        ({"path": "faturas/ghost.pdf"}, 404, "not_found"),
        ({"ids": ["tx_ghost"]}, 422, "not_found"),
    ],
)
def test_review_confirm_errors(scanned: Api, body: dict[str, Any], status: int, code: str) -> None:
    r = scanned.post("/api/review/confirm", body)
    assert r.status_code == status
    assert error_code(r) == code


# ---------------------------------------------------------------- imported transactions


def test_imported_transaction_values_are_read_only(confirmed: Api) -> None:
    tx = next(
        t for t in confirmed.get("/api/transactions").json() if t["description"] == "POSTO SHELL"
    )
    url = f"/api/transactions/{tx['id']}"
    for change in (
        {"amount": "1.00"},
        {"description": "X"},
        {"purchase_date": "2026-09-01"},
        {"provisional": True},
    ):
        r = confirmed.patch(url, change)
        assert r.status_code == 422, change
        assert error_code(r) == "imported_readonly"
    assert confirmed.get(url).json()["amount"] == "200.00"


def test_imported_transaction_category_and_split_can_be_edited(confirmed: Api) -> None:
    tx = next(
        t for t in confirmed.get("/api/transactions").json() if t["description"] == "POSTO SHELL"
    )
    url = f"/api/transactions/{tx['id']}"
    r = confirmed.patch(
        url,
        {
            "category_id": "cat_pets",
            "note": "carro",
            "allocations": [{"user_id": "usr_ana", "pct": "100.00"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["category_id"] == "cat_pets"
    assert r.json()["allocation_origin"] == "manual"
    assert confirmed.get(url).json()["note"] == "carro"


def test_reprocess_confirmed_file_keeps_its_transactions_and_edits(confirmed: Api) -> None:
    tx = next(
        t for t in confirmed.get("/api/transactions").json() if t["description"] == "POSTO SHELL"
    )
    confirmed.patch(f"/api/transactions/{tx['id']}", {"category_id": "cat_pets", "note": "carro"})
    r = confirmed.post("/api/sync/reprocess", {"path": INVOICE})
    assert r.status_code == 200, r.text
    txs = {t["description"]: t for t in confirmed.get("/api/transactions").json()}
    assert set(txs) == {"IFOOD RESTAURANTE", "POSTO SHELL"}
    assert txs["POSTO SHELL"]["category_id"] == "cat_pets"
    assert txs["POSTO SHELL"]["note"] == "carro"


def test_reprocess_pending_file_keeps_it_in_review(scanned: Api) -> None:
    r = scanned.post("/api/sync/reprocess", {"path": INVOICE})
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "reprocess"
    assert set(_review_lines(scanned)) == {"IFOOD RESTAURANTE", "POSTO SHELL"}


def test_imported_transaction_cannot_be_deleted(confirmed: Api) -> None:
    tx = confirmed.get("/api/transactions").json()[0]
    r = confirmed.delete(f"/api/transactions/{tx['id']}")
    assert r.status_code == 422
    assert error_code(r) == "imported_delete"
    assert confirmed.get(f"/api/transactions/{tx['id']}").status_code == 200


def test_card_with_imported_transactions_cannot_be_deleted(confirmed: Api) -> None:
    r = confirmed.delete("/api/cards/card_add")
    assert r.status_code == 409
    assert error_code(r) == "in_use"


def test_recategorize_imported_transaction(confirmed: Api) -> None:
    tx = confirmed.get("/api/transactions").json()[0]
    r = confirmed.post(
        "/api/transactions/recategorize", {"ids": [tx["id"]], "category_id": "cat_pets"}
    )
    assert r.json() == {"updated": 1}


def test_summary_counts_confirmed_invoice(confirmed: Api) -> None:
    s = confirmed.get("/api/reports/summary", params={"month": "2026-10"}).json()
    assert s["total"] == "245.90"
    assert s["states"]


def test_staged_lines_count_only_with_include_pending(scanned: Api) -> None:
    base = scanned.get("/api/reports/summary", params={"month": "2026-10"}).json()
    pending = scanned.get(
        "/api/reports/summary", params={"month": "2026-10", "include_pending": True}
    ).json()
    assert base["total"] == "0.00"
    assert pending["total"] == "245.90"


# ---------------------------------------------------------------- sync file actions


def test_reprocess_unknown_file_is_404(world: Api) -> None:
    r = world.post("/api/sync/reprocess", {"path": "faturas/ghost.pdf"})
    assert r.status_code == 404
    assert error_code(r) == "not_found"


@pytest.mark.parametrize("url", ["/api/sync/supersede/approve", "/api/sync/supersede/reject"])
def test_supersede_actions_on_file_without_candidate(scanned: Api, url: str) -> None:
    r = scanned.post(url, {"path": INVOICE})
    assert r.status_code in (404, 422)
    assert error_code(r) in ("not_found", "sync_error")


def test_choose_owner_requires_card_or_account(scanned: Api) -> None:
    r = scanned.post("/api/sync/choose-owner", {"path": INVOICE})
    assert r.status_code == 422
    assert error_code(r) == "owner_required"
    r = scanned.post("/api/sync/choose-owner", {"path": INVOICE, "card_id": "card_ghost"})
    assert error_code(r) == "reference_not_found"


def test_choose_owner_for_file_awaiting_card(world: Api, settings: Settings) -> None:
    """A card hint that matches no card leaves the file awaiting a card (R4.8)."""
    shutil.copy(EXAMPLES / "inter-fatura.yaml", settings.profiles_dir / "inter-fatura.yaml")
    write(
        settings.inbox_dir / INVOICE,
        inter_invoice([Line(5, 9, 2026, "X", "10.00", card="9090")], main_card="9090"),
    )
    world.post("/api/sync/scan")
    [f] = world.get("/api/sync/status").json()["files"]
    assert f["status"] == "awaiting_card"
    alerts = world.get("/api/alerts").json()
    assert any(a["type"] == "files_need_attention" and INVOICE in a["paths"] for a in alerts)
    r = world.post(
        "/api/sync/choose-owner",
        {"path": INVOICE, "card_id": "card_main", "invoice_month": "2026-10"},
    )
    assert r.status_code == 200, r.text
    [f] = world.get("/api/sync/status").json()["files"]
    assert f["status"] == "pending_review"
    assert f["card_id"] == "card_main"


def test_file_without_profile_is_unknown(world: Api, settings: Settings) -> None:
    write(settings.inbox_dir / INVOICE, inter_invoice(_lines()))
    world.post("/api/sync/scan")
    [f] = world.get("/api/sync/status").json()["files"]
    assert f["status"] == "unknown_profile"


# ---------------------------------------------------------------- R4.3 profiles


def test_r4_3_list_profiles_with_file_counts(scanned: Api) -> None:
    body = scanned.get("/api/profiles").json()
    [p] = [p for p in body["profiles"] if p["id"] == "inter-fatura"]
    assert p["kind"] == "fatura" and p["format"] == "pdf"
    assert p["file"] == "inter-fatura.yaml"
    assert p["files"] == 1 and p["errors"] == 0
    assert not body["errors"]
    assert isinstance(body["examples"], list)


def test_r4_3_get_profile_yaml(inbox: Api) -> None:
    assert inbox.get("/api/profiles/inter-fatura").json() == {
        "id": "inter-fatura",
        "yaml": INTER_YAML,
    }
    r = inbox.get("/api/profiles/ghost")
    assert r.status_code == 404
    assert error_code(r) == "not_found"


def test_r4_3_validate_profile(api: Api) -> None:
    assert api.post("/api/profiles/validate", {"yaml": INTER_YAML}).json() == {
        "valid": True,
        "id": "inter-fatura",
    }
    bad = api.post("/api/profiles/validate", {"yaml": "id: x\nkind: nope\n"}).json()
    assert bad["valid"] is False and bad["error"]
    broken = api.post("/api/profiles/validate", {"yaml": "id: [unclosed"}).json()
    assert broken["valid"] is False


@pytest.mark.parametrize(
    ("profile_id", "yaml", "code"),
    [
        ("Bad_Id", INTER_YAML, "invalid_id"),
        ("inter-fatura", "id: inter-fatura\nkind: nope\n", "invalid_profile"),
        ("outro-banco", INTER_YAML, "id_mismatch"),
    ],
)
def test_r4_3_save_invalid_profile_is_422(
    api: Api, settings: Settings, profile_id: str, yaml: str, code: str
) -> None:
    r = api.put(f"/api/profiles/{profile_id}", {"yaml": yaml})
    assert r.status_code == 422
    assert error_code(r) == code
    assert list(settings.profiles_dir.glob("*.yaml")) == []


def test_r4_3_save_profile_writes_file_and_reprocesses_failed(
    world: Api, settings: Settings
) -> None:
    world.create(
        "cards",
        {
            "id": "card_add",
            "name": "Adicional",
            "parent_card_id": "card_main",
            "last_digits": ["5678"],
        },
    )
    write(settings.inbox_dir / INVOICE, inter_invoice(_lines()))
    world.post("/api/sync/scan")
    assert world.get("/api/sync/status").json()["files"][0]["status"] == "unknown_profile"

    r = world.put("/api/profiles/inter-fatura", {"yaml": INTER_YAML})
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == "inter-fatura"
    assert r.json()["job"]["kind"] == "reprocess_failed"
    assert (settings.profiles_dir / "inter-fatura.yaml").read_text("utf-8") == INTER_YAML
    assert world.get("/api/sync/status").json()["files"][0]["status"] == "pending_review"


def test_r4_3_test_profile_shows_recognized_and_ignored_lines(inbox: Api) -> None:
    r = inbox.post("/api/profiles/test", {"yaml": INTER_YAML, "path": INVOICE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True and body["detected"] is True and body["status"] == "ok"
    assert body["header"]["total"] == "245.90"
    assert body["header"]["due_date"] == "2026-10-15"
    assert {ln["description"] for ln in body["lines"]} == {
        "IFOOD RESTAURANTE",
        "POSTO SHELL",
        "PAGAMENTO ON LINE",
    }
    assert any(i.startswith("Total CARTÃO") for i in body["ignored"])
    assert body["unrecognized"] == []
    # the test never imports anything
    assert inbox.get("/api/sync/status").json()["files"] == []


def test_r4_3_test_unsaved_profile_reports_unrecognized_lines(inbox: Api) -> None:
    narrow = INTER_YAML.replace("(?P<desc>.+?)", "(?P<desc>POSTO.+?)")
    assert narrow != INTER_YAML
    body = inbox.post("/api/profiles/test", {"yaml": narrow, "path": INVOICE}).json()
    assert [ln["description"] for ln in body["lines"]] == ["POSTO SHELL"]
    assert any("IFOOD RESTAURANTE" in u for u in body["unrecognized"])


def test_r4_3_test_profile_that_does_not_detect(world: Api, settings: Settings) -> None:
    write(
        settings.inbox_dir / "faturas" / "y-2026-10.csv",
        open_invoice_csv([("01/10/2026", "LOJA", "10,00", "")]),
    )
    body = world.post(
        "/api/profiles/test", {"yaml": INTER_YAML, "path": "faturas/y-2026-10.csv"}
    ).json()
    assert body["valid"] is True
    assert body["detected"] is False
    assert body["lines"] == []


def test_r4_3_test_csv_profile(world: Api, settings: Settings) -> None:
    write(
        settings.inbox_dir / "faturas" / "y-2026-10.csv",
        open_invoice_csv(
            [("01/10/2026", "LOJA A", "10,00", ""), ("02/10/2026", "LOJA B", "1.234,56", "2/3")]
        ),
    )
    body = world.post(
        "/api/profiles/test", {"yaml": OPEN_INVOICE_CSV_PROFILE, "path": "faturas/y-2026-10.csv"}
    ).json()
    assert body["detected"] is True
    assert [ln["amount"] for ln in body["lines"]] == ["10.00", "1234.56"]


def test_r4_3_test_profile_errors(inbox: Api) -> None:
    r = inbox.post("/api/profiles/test", {"yaml": INTER_YAML, "path": "faturas/ghost.pdf"})
    assert r.status_code == 404
    body = inbox.post("/api/profiles/test", {"yaml": "id: [x", "path": INVOICE}).json()
    assert body["valid"] is False and body["error"]


def test_r4_3_raw_text_of_pdf_and_csv(inbox: Api, settings: Settings) -> None:
    pages = inbox.post("/api/profiles/raw-text", {"path": INVOICE}).json()["pages"]
    assert len(pages) == 4
    assert "Despesas da fatura" in pages[2]
    assert "IFOOD RESTAURANTE" in pages[2]
    write(settings.inbox_dir / "faturas" / "y.csv", b"Data;Valor\n01/10/2026;1,00\n")
    csv = inbox.post("/api/profiles/raw-text", {"path": "faturas/y.csv"}).json()
    assert csv == {"pages": ["Data;Valor\n01/10/2026;1,00\n"]}
    r = inbox.post("/api/profiles/raw-text", {"path": "faturas/ghost.pdf"})
    assert r.status_code == 404


def test_r4_3_raw_text_of_protected_pdf_without_password(world: Api, settings: Settings) -> None:
    from fixtures.files import pdf_bytes

    write(settings.inbox_dir / "faturas" / "locked.pdf", pdf_bytes([["SEGREDO"]], password="x1"))
    r = world.post("/api/profiles/raw-text", {"path": "faturas/locked.pdf"})
    assert r.status_code == 422
    assert error_code(r) == "password"
    assert "x1" not in r.text


def test_profile_examples_dir_is_resolvable() -> None:
    assert Path(EXAMPLES / "inter-fatura.yaml").is_file()


def test_r4_3_example_profiles_can_be_loaded(tmp_path, clock) -> None:  # type: ignore[no-untyped-def]
    import shutil
    from pathlib import Path

    from fastapi.testclient import TestClient

    from expense_tracker.api.app import create_app
    from expense_tracker.config import Settings

    examples = Path(__file__).resolve().parents[3] / "profiles" / "examples"
    local = tmp_path / "examples"
    shutil.copytree(examples, local)
    for d in ("data", "inbox", "profiles"):
        (tmp_path / d).mkdir()
    settings = Settings(
        data_dir=tmp_path / "data",
        inbox_dir=tmp_path / "inbox",
        profiles_dir=tmp_path / "profiles",
        secrets_file=tmp_path / "s.yaml",
        enable_watcher=False,
        examples_dir=local,
    )
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as client:
        listed = client.get("/api/profiles").json()["examples"]
        assert "inter-fatura" in listed and "nubank-fatura" in listed
        got = client.get("/api/profiles/examples/inter-fatura").json()
        assert got["id"] == "inter-fatura" and "Despesas da fatura" in got["yaml"]
        assert client.get("/api/profiles/examples/nope").status_code == 404
        assert client.get("/api/profiles/examples/..%2Fx").status_code in (404, 422)


def test_r4_8_creating_the_card_retries_files_awaiting_it(tmp_path, clock) -> None:  # type: ignore[no-untyped-def]
    import shutil
    from pathlib import Path

    from fastapi.testclient import TestClient

    from expense_tracker.api.app import create_app
    from expense_tracker.config import Settings
    from fixtures.files import Line, inter_invoice, write

    examples = Path(__file__).resolve().parents[3] / "profiles" / "examples"
    for d in ("data", "inbox", "profiles"):
        (tmp_path / d).mkdir()
    for p in examples.glob("*.yaml"):
        shutil.copy(p, tmp_path / "profiles" / p.name)
    (tmp_path / "s.yaml").write_text("{}")
    settings = Settings(
        data_dir=tmp_path / "data",
        inbox_dir=tmp_path / "inbox",
        profiles_dir=tmp_path / "profiles",
        secrets_file=tmp_path / "s.yaml",
        enable_watcher=False,
    )
    write(
        tmp_path / "inbox/faturas/inter/a.pdf",
        inter_invoice([Line(10, 9, 2026, "MERCADO", "20.00", "1234")], main_card="1234"),
    )
    h = {"X-Requested-With": "t"}
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        c.post("/api/sync/scan", headers=h)
        files = c.get("/api/sync/status").json()["files"]
        assert files[0]["status"] == "awaiting_card"
        c.post("/api/users", json={"id": "eu", "name": "Eu"}, headers=h)
        res = c.post(
            "/api/cards",
            headers=h,
            json={
                "id": "inter",
                "name": "Inter",
                "owners": [{"user_id": "eu", "pct": "100"}],
                "responsible_user_id": "eu",
                "profile_id": "inter-fatura",
                "billing_history": [{"from_month": "2026-01", "closing_day": 8, "due_day": 15}],
            },
        )
        assert res.status_code == 201
        files = c.get("/api/sync/status").json()["files"]
        assert files[0]["status"] == "pending_review"
