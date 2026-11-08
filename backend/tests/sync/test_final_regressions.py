"""Regressions for the final review and refutation findings (P1/P2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sync_env import Env, inter, make_env, open_invoice_csv

from expense_tracker.services.catalog import Catalog
from expense_tracker.services.reports import Reports

X = (1, "MERCADO A", "10.00")
Y = (2, "PADARIA B", "5.50")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


def test_r3_6_move_and_copy_in_the_same_scan_never_loses_confirmed_lines(env: Env) -> None:
    # refuter P1: mv a -> b and cp b -> c in one scan must give one MOVED and one DUPLICATE
    env.put("faturas/inter/a.pdf", inter(X, Y))
    env.scan()
    env.confirm_all("faturas/inter/a.pdf")
    env.mv("faturas/inter/a.pdf", "faturas/inter/2026/a (1).pdf")
    data = (env.inbox / "faturas/inter/2026/a (1).pdf").read_bytes()
    env.put("faturas/inter/copia.pdf", data)
    report = env.scan()
    assert len(report.moved) == 1
    assert len(report.duplicate) == 1
    env.rm(report.duplicate[0])
    env.scan()
    assert len(env.repo.all("transactions")) == 2
    assert env.total_confirmed() == "15.50"


def test_r3_7_removing_original_promotes_identical_duplicate_keeping_confirmations(
    env: Env,
) -> None:
    # refuter P2: the byte-identical copy takes over (like MOVED), no re-review
    env.put("faturas/inter/a.pdf", inter(X, Y))
    env.scan()
    env.confirm_all("faturas/inter/a.pdf")
    env.put("faturas/inter/b.pdf", (env.inbox / "faturas/inter/a.pdf").read_bytes())
    env.scan()
    assert env.entry("faturas/inter/b.pdf").status == "duplicate"
    env.rm("faturas/inter/a.pdf")
    env.scan()
    b = env.entry("faturas/inter/b.pdf")
    assert b.status == "confirmed"
    assert env.descs(env.confirmed("faturas/inter/b.pdf")) == {"MERCADO A", "PADARIA B"}
    assert env.staged() == []


def test_r3_3_unreadable_new_version_keeps_previous_confirmations(env: Env) -> None:
    # review P2-5: a transient failure must not delete what was confirmed
    env.put("faturas/inter/a.pdf", inter(X, Y))
    env.scan()
    env.confirm_all("faturas/inter/a.pdf")
    env.put("faturas/inter/a.pdf", b"%PDF-1.4 broken")
    env.scan()
    entry = env.entry("faturas/inter/a.pdf")
    assert entry.status == "confirmed"
    assert any("nova versão não pôde ser lida" in w for w in entry.warnings)
    assert env.total_confirmed() == "15.50"


def test_r3_13_anticipation_without_amount_keeps_plan_as_manual(env: Env) -> None:
    # refuter P2: any anticipation registered by me is an edit (docs/05 cascade)
    env.put("faturas/inter/a.pdf", inter((5, "LOJA TV (Parcela 01 de 10)", "100.00")))
    env.scan()
    env.confirm_all("faturas/inter/a.pdf")
    [plan] = env.repo.all("installment_plans")
    env.repo.put(
        "installment_plans",
        plan.model_copy(
            update={
                "anticipation": plan.anticipation
                or __import__(
                    "expense_tracker.domain.models", fromlist=["Anticipation"]
                ).Anticipation(from_n=5, target_month="2026-11")
            }
        ),
    )
    env.rm("faturas/inter/a.pdf")
    env.scan()
    [kept] = env.repo.all("installment_plans")
    assert kept.origin.type == "manual" and "origem removida" in kept.warnings
    assert kept.anticipation is not None and kept.anticipation.from_n == 5


def test_r4_11_carry_over_keeps_plan_link_without_duplicating_projection(env: Env) -> None:
    # review P1-2: CSV line 1/10 creates a plan; PDF prints the description differently
    Catalog(env.repo).create("categories", {"id": "cat_x", "name": "X"})
    csv_path, pdf_path = "faturas/y/2026-10.csv", "faturas/y/2026-10-fechada.pdf"
    env.put(csv_path, open_invoice_csv([("01/09/2026", "LOJA XPTO", "100,00", "1/10")]))
    env.scan()
    env.confirm_all(csv_path)
    [plan] = env.repo.all("installment_plans")
    env.repo.put(
        "installment_plans",
        plan.model_copy(
            update={
                "allocations": [
                    {"user_id": "usr_me", "pct": "50"},
                    {"user_id": "usr_ana", "pct": "50"},
                ]
            }
        ),
    )
    reports = Reports(env.repo, env.clock.today())
    before = reports.summary("2026-11", None, False)["total"]
    env.put(
        pdf_path,
        inter((1, "LOJA XPTO SAO PAULO (Parcela 01 de 10)", "100.00"), main="9999", card="9999"),
    )
    env.scan()
    env.engine.approve_supersession(pdf_path)
    env.confirm_all(pdf_path) if env.staged(pdf_path) else None
    plans = env.repo.all("installment_plans")
    assert len(plans) == 1
    assert plans[0].origin.type == "import"
    assert reports.summary("2026-11", None, False)["total"] == before == "100.00"


def test_alert_when_active_file_has_no_stored_lines(env: Env) -> None:
    env.put("faturas/inter/a.pdf", inter(X, Y))
    env.scan()
    env.confirm_all("faturas/inter/a.pdf")
    for tx in env.repo.all("transactions"):
        env.repo.delete("transactions", tx.id)  # simulate silent loss
    alerts = Reports(env.repo, env.clock.today()).alerts({})
    bad = [a for a in alerts if a["type"] == "inconsistent_files"]
    assert bad and bad[0]["paths"] == ["faturas/inter/a.pdf"]
