"""R14.16: manual entries saved on "Padrão" before the fix (``allocations = None``) are frozen
once at startup with the split they show today, after a backup of data/."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from conftest import ANA, FOOD, ME, World
from expense_tracker.domain.models import Rule, Share, Source, Transaction
from expense_tracker.services.transactions import Transactions


def _old_entry(w: World, tid: str, description: str, **over: object) -> None:
    data: dict[str, object] = {
        "id": tid,
        "source": Source(type="manual"),
        "card_id": "card_inter",
        "purchase_date": date(2026, 9, 20),
        "invoice_month": "2026-10",
        "description": description,
        "amount": Decimal("100.00"),
        "category_id": FOOD,
        **over,
    }
    w.repo.put("transactions", Transaction(**data))  # type: ignore[arg-type]


def test_r14_16_old_padrao_entries_are_frozen_once_with_a_backup(world: World) -> None:
    world.base()
    shares = [Share(user_id=ME, pct=Decimal("50")), Share(user_id=ANA, pct=Decimal("50"))]
    world.repo.put(
        "rules",
        Rule.model_validate(
            {"id": "rule_m", "priority": 1, "when": {"description_regex": "MERCADO"},
             "then": {"allocations": [s.model_dump() for s in shares]}}
        ),
    )  # fmt: skip
    _old_entry(world, "t_rule", "MERCADO")
    _old_entry(world, "t_owner", "PADARIA")
    explicit = [Share(user_id=shares[0].user_id, pct=Decimal("100"))]
    _old_entry(world, "t_mine", "MERCADO", allocations=explicit, allocation_origin="manual")
    service = Transactions(world.repo, world.clock.today(), world.clock.now)
    backups = world.repo.data_dir / ".backups"
    before = set(backups.iterdir()) if backups.is_dir() else set()

    assert service.freeze_default_splits() == 2
    by_id = {t.id: t for t in world.repo.all("transactions")}
    assert by_id["t_rule"].allocation_origin == "rule:rule_m"
    assert by_id["t_owner"].allocation_origin.startswith("owners:")
    assert by_id["t_mine"].allocations == explicit  # an explicit split is never touched
    assert next(p.name for p in set(backups.iterdir()) - before).endswith("padrao-freeze")
    # second start: nothing left to freeze, no new backup
    assert service.freeze_default_splits() == 0
