"""Test environment for the sync engine: isolated dirs, example profiles and a small catalog.

Everything is synthetic (docs/11): no real invoices or personal data are read.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings
from expense_tracker.domain.documents import ManifestEntry
from expense_tracker.domain.models import Transaction
from expense_tracker.review.confirm import Confirmer
from expense_tracker.services.catalog import Catalog
from expense_tracker.services.reports import Reports
from expense_tracker.storage import Repository
from expense_tracker.sync.engine import ScanReport, SyncEngine
from fixtures.files import (
    OPEN_INVOICE_CSV_PROFILE,
    STATEMENT_PROFILE,
    Line,
    inter_invoice,
    nubank_invoice,
    open_invoice_csv,
    statement,
    write,
)

TZ = ZoneInfo("America/Sao_Paulo")
EXAMPLES = Path(__file__).resolve().parents[3] / "profiles" / "examples"

ME = "usr_me"
OTHER = "usr_ana"
CAT = "cat_misc"
ACC = "acc_main"
INTER = "card_inter"
INTER_ADD = "card_inter_add"
NUBANK = "card_nu"
CSVCARD = "card_y"
BILLING = [{"from_month": "2026-01", "closing_day": 5, "due_day": 15}]

__all__ = [
    "ACC",
    "CAT",
    "CSVCARD",
    "INTER",
    "INTER_ADD",
    "ME",
    "NUBANK",
    "OTHER",
    "Env",
    "Line",
    "inter_invoice",
    "nubank_invoice",
    "open_invoice_csv",
    "statement",
]


@dataclass
class Env:
    root: Path
    settings: Settings
    repo: Repository
    clock: FixedClock
    engine: SyncEngine
    sleeps: list[float] = field(default_factory=list)
    _tick: int = 0

    # ------------------------------------------------------------ files

    @property
    def inbox(self) -> Path:
        return self.settings.inbox_dir

    def put(self, rel: str, data: bytes, mtime_ns: int | None = None) -> Path:
        """Write a file. By default the mtime is a whole, ever-increasing second so tests do
        not depend on the filesystem's sub-microsecond timestamps (see the ns-precision test)."""
        path = write(self.inbox / rel, data)
        if mtime_ns is None:
            self._tick += 1
            mtime_ns = (1_790_000_000 + self._tick) * 1_000_000_000
        os.utime(path, ns=(mtime_ns, mtime_ns))
        return path

    def rm(self, rel: str) -> None:
        (self.inbox / rel).unlink()

    def mv(self, src: str, dst: str) -> None:
        target = self.inbox / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        (self.inbox / src).rename(target)

    def scan(self) -> ScanReport:
        return self.engine.scan()

    # ------------------------------------------------------------ queries

    def entry(self, rel: str) -> ManifestEntry:
        entry: ManifestEntry | None = self.repo.get("import_manifest", rel)
        assert entry is not None, f"{rel} not in manifest"
        return entry

    def manifest(self) -> dict[str, ManifestEntry]:
        return {e.path: e for e in self.repo.all("import_manifest")}

    def staged(self, rel: str | None = None) -> list[Transaction]:
        return [t for t in self.repo.all("staging") if rel is None or t.source.path == rel]

    def confirmed(self, rel: str | None = None) -> list[Transaction]:
        return [t for t in self.repo.all("transactions") if rel is None or t.source.path == rel]

    def lines(self, rel: str) -> list[Transaction]:
        return [*self.staged(rel), *self.confirmed(rel)]

    def descs(self, txs: list[Transaction]) -> set[str]:
        return {t.description for t in txs}

    def confirm(self, txs: list[Transaction]) -> dict[str, Any]:
        return Confirmer(self.repo, self.clock.now()).confirm([t.id for t in txs])

    def confirm_all(self, rel: str) -> dict[str, Any]:
        return self.confirm(
            [t for t in self.staged(rel) if t.review and t.review.status != "overlap"]
        )

    def total(self, month: str = "2026-10") -> str:
        out: str = Reports(self.repo, self.clock.today()).summary(
            month, None, include_pending=True
        )["total"]
        return out

    def total_confirmed(self, month: str = "2026-10") -> str:
        out: str = Reports(self.repo, self.clock.today()).summary(
            month, None, include_pending=False
        )["total"]
        return out

    def by_card(self, month: str = "2026-10", pending: bool = True) -> dict[str, str]:
        out: dict[str, str] = Reports(self.repo, self.clock.today()).summary(
            month, None, include_pending=pending
        )["by_card"]
        return out


def make_env(
    root: Path,
    *,
    stable_wait: float = 0,
    sleep: Callable[[float], None] | None = None,
    catalog: bool = True,
    passwords: dict[str, str] | None = None,
) -> Env:
    data = root / "data"
    inbox = root / "inbox"
    profiles = root / "profiles"
    for d in (data, inbox / "faturas", inbox / "extratos", profiles):
        d.mkdir(parents=True, exist_ok=True)
    for src in EXAMPLES.glob("*.yaml"):
        shutil.copy(src, profiles / src.name)
    (profiles / "banco-teste-extrato.yaml").write_text(STATEMENT_PROFILE, encoding="utf-8")
    (profiles / "banco-y-fatura-aberta-csv.yaml").write_text(
        OPEN_INVOICE_CSV_PROFILE, encoding="utf-8"
    )
    secrets = root / "secrets.yaml"
    secrets.write_text(
        "".join(f"{k}: {v!r}\n" for k, v in (passwords or {}).items()) or "{}\n",
        encoding="utf-8",
    )
    settings = Settings(
        data_dir=data,
        inbox_dir=inbox,
        profiles_dir=profiles,
        secrets_file=secrets,
        scan_interval_seconds=60,
        parse_timeout_seconds=20,
        backups_keep=3,
        enable_watcher=False,
    )
    repo = Repository(data, backups_keep=3).open()
    clock = FixedClock(datetime(2026, 10, 12, 10, 0, tzinfo=TZ))
    env = Env(root, settings, repo, clock, None)  # type: ignore[arg-type]

    def fake_sleep(seconds: float) -> None:
        env.sleeps.append(seconds)

    env.engine = SyncEngine(
        repo, settings, clock, stable_wait=stable_wait, sleep=sleep or fake_sleep
    )
    if catalog:
        seed_catalog(repo)
    return env


def seed_catalog(repo: Repository) -> None:
    cat = Catalog(repo)
    me_only = [{"user_id": ME, "pct": "100"}]
    cat.create("users", {"id": ME, "name": "Eu"})
    cat.create("users", {"id": OTHER, "name": "Ana", "aliases": ["ANA SOUZA"]})
    cat.create("categories", {"id": CAT, "name": "Diversos"})
    cat.create(
        "rules",
        {"id": "rule_all", "when": {"description_regex": "."}, "then": {"category_id": CAT}},
    )
    cat.create(
        "accounts",
        {
            "id": ACC,
            "name": "Conta",
            "owners": me_only,
            "responsible_user_id": ME,
            "profile_id": "banco-teste-extrato",
            "account_hint": "12345-6",
        },
    )
    cat.create(
        "cards",
        {
            "id": INTER,
            "name": "Inter",
            "owners": me_only,
            "responsible_user_id": ME,
            "account_id": ACC,
            "billing_history": BILLING,
            "last_digits": ["1234"],
            "profile_id": "inter-fatura",
        },
    )
    cat.create(
        "cards",
        {
            "id": INTER_ADD,
            "name": "Inter virtual",
            "parent_card_id": INTER,
            "last_digits": ["5678"],
            "profile_id": "inter-fatura",
        },
    )
    cat.create(
        "cards",
        {
            "id": NUBANK,
            "name": "Nubank",
            "owners": me_only,
            "responsible_user_id": ME,
            "billing_history": BILLING,
            "last_digits": ["1111"],
            "profile_id": "nubank-fatura",
        },
    )
    cat.create(
        "cards",
        {
            "id": CSVCARD,
            "name": "Banco Y",
            "owners": me_only,
            "responsible_user_id": ME,
            "billing_history": BILLING,
            "last_digits": ["9999"],
            "profile_id": "banco-y-fatura-aberta-csv",
        },
    )


L = Line


def inter(*items: tuple[int, str, str], main: str = "1234", card: str = "5678") -> bytes:
    """Inter-like invoice for 2026-10 (due 15/10) with (day-of-september, desc, amount)."""
    return inter_invoice(
        [L(d, 9, 2026, desc, amt, card=card) for d, desc, amt in items], main_card=main
    )
