"""R8.9 + R3.4 (operator report): deleting the only invoice of a card must not leave
"Fatura faltando" alerts for months that never had activity."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sync_env import INTER, TZ, Env, inter, make_env

from expense_tracker.domain.ledger import Ledger
from expense_tracker.domain.models import Source, Transaction
from expense_tracker.services.reports import Reports, build_state

INV = "faturas/inter/2026-10.pdf"
A = (1, "MERCADO A", "10.00")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


def _missing(env: Env) -> list[str]:
    alerts = Reports(env.repo, env.clock.today()).alerts({})
    return sorted(a["month"] for a in alerts if a["type"] == "missing_invoice")


def test_r8_9_deleted_only_invoice_leaves_no_missing_months(env: Env) -> None:
    env.put(INV, inter(A))
    env.scan()
    env.confirm_all(INV)
    env.rm(INV)
    env.scan()
    assert env.confirmed() == []
    # a manual entry in the open invoice says nothing about the months before it
    h = Ledger(build_state(env.repo), env.clock.today()).card_h(INTER)
    env.repo.put(
        "transactions",
        Transaction(
            id="man_open",
            source=Source(type="manual"),
            card_id=INTER,
            purchase_date=env.clock.today(),
            invoice_month=h,
            description="PADARIA",
            amount=Decimal("8.00"),
            category_id="cat_x",
        ),
    )
    assert _missing(env) == []


def test_r8_9_months_after_the_first_invoice_are_missing(env: Env) -> None:
    env.put(INV, inter(A))
    env.scan()
    env.confirm_all(INV)
    # months later, with no newer invoice: the gaps after the imported one are missing
    env.clock.set(datetime(2027, 2, 1, 10, 0, tzinfo=TZ))
    got = _missing(env)
    assert got, "the months after the last imported invoice must be reported"
    assert "2026-12" in got
    assert all(m > "2026-10" for m in got)  # never the imported month or before it
