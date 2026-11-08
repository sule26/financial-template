"""Fixtures for review tests: a real pipeline (Repository + Catalog + SyncEngine) on tmp dirs."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings
from expense_tracker.domain.documents import ManifestEntry
from expense_tracker.domain.ledger import Ledger
from expense_tracker.domain.models import Transaction
from expense_tracker.review.confirm import Confirmer
from expense_tracker.services.catalog import Catalog
from expense_tracker.services.reports import Reports
from expense_tracker.services.transactions import ManualEntry, Transactions
from expense_tracker.storage import Repository
from expense_tracker.sync.engine import SyncEngine
from fixtures.files import STATEMENT_PROFILE, write

EXAMPLES = Path(__file__).resolve().parents[3] / "profiles" / "examples"

ME = "u_me"
ANA = "u_ana"  # partner
PAI = "u_pai"  # parent (sends PIX)

FOOD = "cat_food"
HOME = "cat_home"
TECH = "cat_tech"
FUN = "cat_fun"


class World:
    """End-to-end harness: drop files in the inbox, scan, confirm, read reports."""

    def __init__(self, settings: Settings, clock: FixedClock) -> None:
        self.settings = settings
        self.clock = clock
        for p in EXAMPLES.glob("*.yaml"):
            shutil.copy(p, settings.profiles_dir / p.name)
        (settings.profiles_dir / "statement.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
        self.repo = Repository(settings.data_dir).open()
        self.catalog = Catalog(self.repo)
        self.engine = SyncEngine(self.repo, settings, clock, stable_wait=0)
        self.txs = Transactions(
            self.repo,
            clock.now().date(),
            clock.now,
            after_manual_change=lambda tx: self._reconcile_manual(tx),
        )

    def _reconcile_manual(self, tx: Transaction) -> dict[str, Any]:
        from expense_tracker.review.actions import reconcile_manual

        return reconcile_manual(self.repo, tx, self.clock.now())

    # ------------------------------------------------------------ catalog

    def base(self) -> World:
        c = self.catalog
        c.create("users", {"id": ME, "name": "Eu"})
        c.create("users", {"id": ANA, "name": "Ana"})
        c.create("users", {"id": PAI, "name": "Pai", "aliases": ["JOSE DA SILVA"]})
        for cid, name in ((FOOD, "Mercado"), (HOME, "Casa"), (TECH, "Tecnologia"), (FUN, "Lazer")):
            c.create("categories", {"id": cid, "name": name})
        c.create(
            "accounts",
            {
                "id": "acc_me",
                "name": "Conta",
                "owners": [{"user_id": ME, "pct": "100"}],
                "responsible_user_id": ME,
                "profile_id": "banco-teste-extrato",
                "account_hint": "12345-6",
            },
        )
        c.create(
            "cards",
            {
                "id": "card_inter",
                "name": "Inter",
                "owners": [{"user_id": ME, "pct": "100"}],
                "responsible_user_id": ME,
                "last_digits": ["1234", "5678"],
                "profile_id": "inter-fatura",
                "billing_history": [{"from_month": "2026-01", "closing_day": 5, "due_day": 15}],
            },
        )
        return self

    def nubank(self, **extra: Any) -> None:
        data = {
            "id": "card_nu",
            "name": "Nubank",
            "owners": [{"user_id": ME, "pct": "100"}],
            "responsible_user_id": ME,
            "last_digits": ["1111"],
            "profile_id": "nubank-fatura",
            "billing_history": [{"from_month": "2026-01", "closing_day": 10, "due_day": 19}],
        }
        data.update(extra)
        self.catalog.create("cards", data)

    def rule(self, regex: str, category: str, priority: int = 100, **then: Any) -> None:
        self.catalog.create(
            "rules",
            {
                "priority": priority,
                "when": {"description_regex": regex},
                "then": {"category_id": category, **then},
            },
        )

    def categorize_all(self, category: str = FOOD) -> None:
        self.rule(".*", category, priority=1000)

    # ------------------------------------------------------------ inbox

    def drop(self, rel: str, data: bytes) -> str:
        write(self.settings.inbox_dir / rel, data)
        self.engine.scan()
        return rel

    def remove(self, rel: str) -> None:
        (self.settings.inbox_dir / rel).unlink()
        self.engine.scan()

    def entry(self, rel: str) -> ManifestEntry:
        e = self.repo.get("import_manifest", rel)
        assert e is not None, f"{rel} not in manifest"
        return e

    def staged(self, rel: str | None = None) -> list[Transaction]:
        sha = self.entry(rel).sha256 if rel else None
        items = [t for t in self.repo.all("staging") if sha is None or t.source.sha256 == sha]
        return sorted(items, key=lambda t: t.source.line or 0)

    def staged_by_desc(self, text: str, rel: str | None = None) -> Transaction:
        found = [t for t in self.staged(rel) if text in t.description]
        assert len(found) == 1, f"{text!r}: {[t.description for t in self.staged(rel)]}"
        return found[0]

    def confirmed(self) -> list[Transaction]:
        return self.repo.all("transactions")

    def confirm(self, rel: str) -> dict[str, Any]:
        return self.confirmer().confirm([t.id for t in self.staged(rel)])

    def confirmer(self) -> Confirmer:
        return Confirmer(self.repo, self.clock.now())

    # ------------------------------------------------------------ manual

    def manual(self, **data: Any) -> dict[str, Any]:
        return self.txs.create_manual(ManualEntry(**data))

    # ------------------------------------------------------------ reports

    def reports(self) -> Reports:
        return Reports(self.repo, self.clock.now().date())

    def ledger(self, include_pending: bool = False) -> Ledger:
        return self.reports().ledger(include_pending)

    def month_total(self, month: str, include_pending: bool = False) -> Decimal:
        return Decimal(self.reports().summary(month, None, include_pending)["total"])

    def projection(self, include_pending: bool = False) -> dict[str, Decimal]:
        p = self.reports().projection(None, include_pending)
        return {m["month"]: Decimal(m["total"]) for m in p["months"]}


@pytest.fixture
def world(settings: Settings, clock: FixedClock) -> Iterator[World]:
    w = World(settings, clock)
    try:
        yield w
    finally:
        w.repo.close()


def d(y: int, m: int, day: int) -> date:
    return date(y, m, day)


NOW = datetime(2026, 10, 12, 10, 0)
