"""Inbox folders per card/account (R4.8) and identification by folder + file name.

Everything is synthetic (docs/11): files come from ``fixtures.files``.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from expense_tracker.api.app import create_app
from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings
from expense_tracker.domain.documents import ManifestEntry
from expense_tracker.services.catalog import Catalog
from expense_tracker.storage import Repository
from expense_tracker.sync.engine import SyncEngine
from fixtures.files import (
    OPEN_INVOICE_CSV_PROFILE,
    STATEMENT_PROFILE,
    Line,
    inter_invoice,
    open_invoice_csv,
    statement,
    write,
)

TZ = ZoneInfo("America/Sao_Paulo")
EXAMPLES = Path(__file__).resolve().parents[3] / "profiles" / "examples"
CSRF = {"X-Requested-With": "pytest"}
BILLING = [{"from_month": "2026-01", "closing_day": 5, "due_day": 15}]
ME = [{"user_id": "usr_me", "pct": "100.00"}]


def _settings(root: Path, examples: Path) -> Settings:
    data, inbox, profiles = root / "data", root / "inbox", root / "profiles"
    for d in (data, inbox / "faturas", inbox / "extratos", profiles):
        d.mkdir(parents=True, exist_ok=True)
    secrets = root / "secrets.yaml"
    secrets.write_text("{}\n", encoding="utf-8")
    return Settings(
        data_dir=data,
        inbox_dir=inbox,
        profiles_dir=profiles,
        secrets_file=secrets,
        parse_timeout_seconds=20,
        backups_keep=3,
        enable_watcher=False,
        examples_dir=examples,
    )


def _dirs(base: Path) -> set[str]:
    return {p.name for p in base.iterdir() if p.is_dir()}


# ---------------------------------------------------------------- folders via the API


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, Settings]]:
    settings = _settings(tmp_path, tmp_path / "no-examples")
    clock = FixedClock(datetime(2026, 10, 12, 10, 0, tzinfo=TZ))
    with TestClient(create_app(settings=settings, clock=clock, start_background=False)) as c:
        r = c.post("/api/users", json={"id": "usr_me", "name": "Eu"}, headers=CSRF)
        assert r.status_code == 201, r.text
        yield c, settings


def _post(c: TestClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    r = c.post(f"/api/{path}", json=body, headers=CSRF)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _card(c: TestClient, name: str, **over: Any) -> dict[str, Any]:
    body = {
        "name": name,
        "owners": ME,
        "responsible_user_id": "usr_me",
        "billing_history": BILLING,
        **over,
    }
    return _post(c, "cards", body)


def _account(c: TestClient, name: str, kind: str) -> dict[str, Any]:
    return _post(
        c,
        "accounts",
        {"name": name, "type": kind, "owners": ME, "responsible_user_id": "usr_me"},
    )


def test_r4_8_r13_2_creating_card_creates_lowercase_invoice_folder(
    client: tuple[TestClient, Settings],
) -> None:
    c, settings = client
    _card(c, "Mercado Pago")
    assert (settings.inbox_dir / "faturas" / "mercado pago").is_dir()
    assert _dirs(settings.inbox_dir / "faturas") == {"mercado pago"}


def test_r4_8_creating_checking_account_creates_statement_folder(
    client: tuple[TestClient, Settings],
) -> None:
    c, settings = client
    _account(c, "Conta Inter", "checking")
    assert (settings.inbox_dir / "extratos" / "conta inter").is_dir()


def test_r4_8_cash_account_creates_no_folder(client: tuple[TestClient, Settings]) -> None:
    c, settings = client
    _account(c, "Carteira", "cash")
    assert _dirs(settings.inbox_dir / "extratos") == set()
    assert _dirs(settings.inbox_dir / "faturas") == set()


def test_r4_8_additional_card_creates_no_folder(client: tuple[TestClient, Settings]) -> None:
    c, settings = client
    main = _card(c, "Inter")
    _post(c, "cards", {"name": "Inter virtual", "parent_card_id": main["id"]})
    assert _dirs(settings.inbox_dir / "faturas") == {"inter"}


def test_r4_8_equivalent_existing_folder_is_not_duplicated(
    client: tuple[TestClient, Settings],
) -> None:
    c, settings = client
    (settings.inbox_dir / "faturas" / "mercado-pago").mkdir()
    _card(c, "Mercado Pago")
    assert _dirs(settings.inbox_dir / "faturas") == {"mercado-pago"}


def test_r4_8_renaming_card_creates_folder_for_new_name(
    client: tuple[TestClient, Settings],
) -> None:
    c, settings = client
    card = _card(c, "Inter")
    body = {k: v for k, v in card.items() if k != "id"} | {"name": "Inter Black"}
    r = c.put(f"/api/cards/{card['id']}", json=body, headers=CSRF)
    assert r.status_code == 200, r.text
    assert "inter black" in _dirs(settings.inbox_dir / "faturas")


def test_r4_8_scan_creates_folders_for_existing_cards_and_accounts(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tmp_path / "no-examples")
    repo = Repository(settings.data_dir, backups_keep=3).open()
    try:
        cat = Catalog(repo)
        cat.create("users", {"id": "usr_me", "name": "Eu"})
        cat.create(
            "cards",
            {
                "id": "card_nu",
                "name": "Nubank",
                "owners": ME,
                "responsible_user_id": "usr_me",
                "billing_history": BILLING,
            },
        )
        cat.create(
            "accounts",
            {
                "id": "acc_x",
                "name": "Conta Itaú",
                "type": "checking",
                "owners": ME,
                "responsible_user_id": "usr_me",
            },
        )
        assert _dirs(settings.inbox_dir / "faturas") == set()  # no engine involved yet
        clock = FixedClock(datetime(2026, 10, 12, 10, 0, tzinfo=TZ))
        SyncEngine(repo, settings, clock, stable_wait=0, sleep=lambda _s: None).scan()
        assert _dirs(settings.inbox_dir / "faturas") == {"nubank"}
        assert _dirs(settings.inbox_dir / "extratos") == {"conta itaú"}
    finally:
        repo.close()


# ---------------------------------------------------------------- identification (R1.13)


class Box:
    """Repo + engine over isolated dirs; profiles/ may be left empty."""

    def __init__(self, root: Path, examples: Path) -> None:
        self.settings = _settings(root, examples)
        self.repo = Repository(self.settings.data_dir, backups_keep=3).open()
        self.cat = Catalog(self.repo)
        self.cat.create("users", {"id": "usr_me", "name": "Eu"})
        self.cat.create("categories", {"id": "cat_x", "name": "Teste"})
        clock = FixedClock(datetime(2026, 10, 12, 10, 0, tzinfo=TZ))
        self.engine = SyncEngine(
            self.repo, self.settings, clock, stable_wait=0, sleep=lambda _s: None
        )
        self._tick = 0

    def card(self, cid: str, name: str) -> None:
        # no last_digits and no profile_id: only the folder can identify it
        self.cat.create(
            "cards",
            {
                "id": cid,
                "name": name,
                "owners": ME,
                "responsible_user_id": "usr_me",
                "billing_history": BILLING,
            },
        )

    def profile(self, name: str, text: str) -> None:
        (self.settings.profiles_dir / f"{name}.yaml").write_text(text, encoding="utf-8")

    def put(self, rel: str, data: bytes) -> None:
        path = write(self.settings.inbox_dir / rel, data)
        self._tick += 1
        ns = (1_790_000_000 + self._tick) * 1_000_000_000
        os.utime(path, ns=(ns, ns))

    def entry(self, rel: str) -> ManifestEntry:
        self.engine.scan()
        found: ManifestEntry | None = self.repo.get("import_manifest", rel)
        assert found is not None, f"{rel} not in manifest"
        return found


@pytest.fixture
def box(tmp_path: Path) -> Iterator[Box]:
    b = Box(tmp_path, EXAMPLES)
    try:
        yield b
    finally:
        b.repo.close()


def _inter(main: str = "4321") -> bytes:
    return inter_invoice([Line(10, 9, 2026, "PADARIA", "25.00", card=main)], main_card=main)


def test_r1_13_r13_3_card_identified_by_folder_name_with_builtin_profiles(box: Box) -> None:
    assert not any(box.settings.profiles_dir.iterdir())  # profiles/ empty: examples are used
    box.card("card_inter", "Inter")
    box.card("card_nu", "Nubank")  # a second card: the folder must decide
    box.put("faturas/inter/2026-10.pdf", _inter())
    e = box.entry("faturas/inter/2026-10.pdf")
    assert e.status not in ("awaiting_card", "unknown_profile", "error"), e
    assert e.profile_id == "inter-fatura"
    assert e.card_id == "card_inter"
    assert e.invoice_month == "2026-10"
    assert not any(w.startswith("filename_month_differs") for w in e.warnings)


def test_r1_13_without_examples_and_empty_profiles_file_is_unknown_profile(
    tmp_path: Path,
) -> None:
    b = Box(tmp_path, tmp_path / "no-examples")
    try:
        b.card("card_inter", "Inter")
        b.put("faturas/inter/2026-10.pdf", _inter())
        assert b.entry("faturas/inter/2026-10.pdf").status == "unknown_profile"
    finally:
        b.repo.close()


def test_r1_13_folder_not_matching_any_card_awaits_card(box: Box) -> None:
    box.card("card_inter", "Inter")
    box.card("card_nu", "Nubank")
    box.put("faturas/outro banco/2026-10.pdf", _inter())
    assert box.entry("faturas/outro banco/2026-10.pdf").status == "awaiting_card"


def test_r1_13_file_at_inbox_top_level_is_not_identified_by_folder(box: Box) -> None:
    box.card("card_inter", "Inter")
    box.card("card_nu", "Nubank")
    box.put("faturas/2026-10.pdf", _inter())
    assert box.entry("faturas/2026-10.pdf").status == "awaiting_card"


@pytest.mark.parametrize("folder", ["ITAÚ", "itau", "Itaú", "ITAU"])
def test_r1_13_folder_match_ignores_case_and_accents(box: Box, folder: str) -> None:
    box.card("card_itau", "Itaú")
    box.card("card_nu", "Nubank")
    rel = f"faturas/{folder}/2026-10.pdf"
    box.put(rel, _inter())
    e = box.entry(rel)
    assert e.card_id == "card_itau", e
    assert e.status != "awaiting_card"


def test_r1_13_folder_with_dashes_matches_name_with_spaces(box: Box) -> None:
    box.card("card_mp", "Mercado Pago")
    box.card("card_nu", "Nubank")
    rel = "faturas/mercado-pago/2026-10.pdf"
    box.put(rel, _inter())
    assert box.entry(rel).card_id == "card_mp"


def test_r1_13_filename_month_differing_from_due_date_warns(box: Box) -> None:
    box.card("card_inter", "Inter")
    box.put("faturas/inter/2026-09.pdf", _inter())
    e = box.entry("faturas/inter/2026-09.pdf")
    assert e.invoice_month == "2026-10"  # the document's due date wins
    assert "filename_month_differs:2026-09" in e.warnings


def test_r1_13_open_csv_without_month_uses_filename_month(box: Box) -> None:
    box.profile("banco-y-fatura-aberta-csv", OPEN_INVOICE_CSV_PROFILE)
    box.card("card_y", "Banco Y")
    box.card("card_nu", "Nubank")
    rel = "faturas/banco y/2026-11.csv"
    box.put(rel, open_invoice_csv([("20/10/2026", "LOJA", "50,00", "")]))
    e = box.entry(rel)
    assert e.status not in ("awaiting_card", "unknown_profile", "error"), e
    assert e.card_id == "card_y"
    assert e.invoice_month == "2026-11"
    assert not any(w.startswith("filename_month_differs") for w in e.warnings)


def test_r1_13_statement_account_identified_by_folder(box: Box) -> None:
    box.profile("banco-teste-extrato", STATEMENT_PROFILE)
    for aid, name in (("acc_inter", "Conta Inter"), ("acc_nu", "Conta Nu")):
        box.cat.create(
            "accounts",
            {
                "id": aid,
                "name": name,
                "type": "checking",
                "owners": ME,
                "responsible_user_id": "usr_me",
            },
        )
    rel = "extratos/conta inter/2026-09.pdf"
    box.put(rel, statement([("05/09/2026", "PADARIA", "12.00")]))
    e = box.entry(rel)
    assert e.status not in ("awaiting_card", "unknown_profile", "error"), e
    assert e.account_id == "acc_inter"


async def test_r13_3_startup_retries_files_that_were_unknown(tmp_path):  # type: ignore[no-untyped-def]
    import asyncio
    import shutil
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from expense_tracker.clock import FixedClock
    from expense_tracker.config import Settings
    from expense_tracker.services.catalog import Catalog
    from expense_tracker.storage import Repository
    from expense_tracker.sync import SyncEngine, SyncService
    from fixtures.files import Line, inter_invoice, write

    examples = Path(__file__).resolve().parents[3] / "profiles" / "examples"
    for d in ("data", "inbox", "profiles", "noexamples"):
        (tmp_path / d).mkdir()
    (tmp_path / "s.yaml").write_text("{}")
    clock = FixedClock(datetime(2026, 10, 12, tzinfo=ZoneInfo("America/Sao_Paulo")))
    repo = Repository(tmp_path / "data").open()
    cat = Catalog(repo)
    cat.create("users", {"id": "eu", "name": "Eu"})
    owners = [{"user_id": "eu", "pct": "100"}]
    cat.create("cards", {"id": "inter", "name": "Inter", "owners": owners,
                         "responsible_user_id": "eu",
                         "billing_history": [{"from_month": "2026-01", "closing_day": 8,
                                              "due_day": 15}]})  # fmt: skip
    write(
        tmp_path / "inbox/faturas/inter/2026-10.pdf",
        inter_invoice([Line(10, 9, 2026, "MERCADO", "20.00", "1234")]),
    )
    old = Settings(data_dir=tmp_path / "data", inbox_dir=tmp_path / "inbox",
                   profiles_dir=tmp_path / "profiles", secrets_file=tmp_path / "s.yaml",
                   enable_watcher=False, examples_dir=tmp_path / "noexamples")  # fmt: skip
    SyncEngine(repo, old, clock, stable_wait=0).scan()
    assert repo.get("import_manifest", "faturas/inter/2026-10.pdf").status == "unknown_profile"
    new = Settings(data_dir=tmp_path / "data", inbox_dir=tmp_path / "inbox",
                   profiles_dir=tmp_path / "profiles", secrets_file=tmp_path / "s.yaml",
                   enable_watcher=False, examples_dir=examples)  # fmt: skip
    service = await SyncService(SyncEngine(repo, new, clock, stable_wait=0), 3600, False).start()
    for _ in range(100):
        await asyncio.sleep(0.05)
        entry = repo.get("import_manifest", "faturas/inter/2026-10.pdf")
        if entry is not None and entry.status == "pending_review":
            break
    await service.stop()
    assert repo.get("import_manifest", "faturas/inter/2026-10.pdf").status == "pending_review"
    repo.close()
    _ = shutil
