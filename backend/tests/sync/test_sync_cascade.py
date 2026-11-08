"""Removal cascade (docs/05 "Cascata de remoção"; R3.13) and its helpers in review.confirm."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sync_env import ACC, CAT, INTER, ME, OTHER, Env, inter, inter_invoice, make_env, statement

from expense_tracker.domain.documents import ManifestEntry
from expense_tracker.domain.models import (
    Anticipation,
    InstallmentPlan,
    InstallmentRef,
    Links,
    Origin,
    Share,
    Source,
    Transaction,
)
from expense_tracker.review.confirm import (
    move_lines,
    refresh_status,
    relink_on_return,
    remove_lines,
)
from expense_tracker.review.fingerprint import derived_id
from expense_tracker.services.catalog import Catalog
from fixtures.files import Line

OCT = "faturas/inter/2026-10.pdf"
NOV = "faturas/inter/2026-11.pdf"
STMT = "extratos/conta/2026-09.pdf"
PARC1 = (5, "LOJA X (Parcela 1 de 3)", "100.00")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


def _plan_line(env: Env, rel: str = OCT) -> Transaction:
    return next(t for t in env.lines(rel) if t.installment is not None)


def _import_plan(env: Env) -> InstallmentPlan:
    env.put(OCT, inter(PARC1, (1, "MERCADO A", "10.00")))
    env.scan()
    line = _plan_line(env)
    assert line.review and [s.type for s in line.review.suggestions] == ["create_plan"]
    env.confirm_all(OCT)
    plan: InstallmentPlan = env.repo.get("installment_plans", derived_id("plan", line.fingerprint))
    assert plan is not None and plan.origin.type == "import"
    return plan


# ---------------------------------------------------------------- plans


def test_r3_13_plan_created_from_line_removed_with_pdf_and_recreated_same_id(env: Env) -> None:
    plan = _import_plan(env)
    data = (env.inbox / OCT).read_bytes()
    env.rm(OCT)
    env.scan()
    assert env.repo.get("installment_plans", plan.id) is None

    env.put(OCT, data)
    env.scan()
    env.confirm_all(OCT)
    back = env.repo.get("installment_plans", plan.id)
    assert back is not None and back.origin.type == "import"
    assert back.total_installments == 3 and back.first_invoice_month == "2026-10"
    assert len(env.repo.all("installment_plans")) == 1


def test_r3_13_plan_with_my_edit_becomes_manual_and_line_relinks_on_return(env: Env) -> None:
    plan = _import_plan(env)
    Catalog(env.repo).update(
        "installment_plans",
        plan.id,
        {
            **plan.model_dump(mode="json", exclude={"id"}),
            "allocations": [{"user_id": ME, "pct": "50"}, {"user_id": OTHER, "pct": "50"}],
        },
    )
    data = (env.inbox / OCT).read_bytes()
    env.rm(OCT)
    env.scan()
    kept = env.repo.get("installment_plans", plan.id)
    assert kept is not None
    assert kept.origin.type == "manual" and kept.origin.fingerprint == plan.origin.fingerprint
    assert kept.warnings  # "origem removida"
    assert kept.allocations is not None

    env.put(OCT, data)
    env.scan()
    # the returning line belongs to the same plan id again; my edit is preserved
    line = _plan_line(env)
    assert line.review and line.review.suggestions[0].target_id == plan.id
    env.confirm_all(OCT)
    assert _plan_line(env).installment.plan_id == plan.id
    assert env.repo.get("installment_plans", plan.id).allocations is not None
    assert len(env.repo.all("installment_plans")) == 1


def test_r3_13_plan_still_referenced_by_another_active_line_is_kept(env: Env) -> None:
    plan = _import_plan(env)
    env.put(
        NOV,
        inter_invoice([Line(5, 9, 2026, "LOJA X (Parcela 2 de 3)", "100.00")], due="15/11/2026"),
    )
    env.scan()
    nov_line = _plan_line(env, NOV)
    assert nov_line.review and nov_line.review.suggestions[0].type == "link_plan"
    assert nov_line.review.suggestions[0].target_id == plan.id
    env.confirm_all(NOV)

    env.rm(OCT)
    env.scan()

    assert env.repo.get("installment_plans", plan.id) is not None
    assert _plan_line(env, NOV).installment.plan_id == plan.id


def test_r3_13_installment_link_goes_with_the_line_and_month_is_projected(env: Env) -> None:
    plan = _import_plan(env)
    env.put(
        NOV,
        inter_invoice([Line(5, 9, 2026, "LOJA X (Parcela 2 de 3)", "100.00")], due="15/11/2026"),
    )
    env.scan()
    env.confirm_all(NOV)
    assert env.total_confirmed("2026-11") == "100.00"

    env.rm(NOV)
    env.scan()

    assert env.lines(NOV) == []
    assert env.repo.get("installment_plans", plan.id) is not None
    # the plan keeps projecting November's installment
    assert env.total_confirmed("2026-11") == "100.00"


# ---------------------------------------------------------------- statement-derived


def _settlement_stmt() -> bytes:
    return statement([("03/09/2026", "PIX RECEBIDO ANA SOUZA", "-30.00")])


def test_r3_13_settlement_becomes_manual_and_is_relinked_on_return(env: Env) -> None:
    env.put(STMT, _settlement_stmt())
    env.scan()
    (line,) = env.staged(STMT)
    assert line.review and line.review.suggestions[0].type == "settlement"
    env.confirm_all(STMT)
    sid = derived_id("set", line.fingerprint)
    assert env.repo.get("settlements", sid).origin.type == "import"

    data = (env.inbox / STMT).read_bytes()
    env.rm(STMT)
    env.scan()
    kept = env.repo.get("settlements", sid)
    assert kept is not None  # never deleted silently
    assert kept.origin.type == "manual" and "origem removida" in kept.warnings

    env.put(STMT, data)
    env.scan()
    back = env.repo.get("settlements", sid)
    assert back.origin.type == "import" and "origem removida" not in back.warnings
    env.confirm_all(STMT)
    assert len(env.repo.all("settlements")) == 1


def test_r3_13_investment_movement_becomes_manual_and_is_relinked(env: Env) -> None:
    inv = Catalog(env.repo).create(
        "investments",
        {
            "id": "inv_cdb",
            "name": "CDB",
            "owners": [{"user_id": ME, "pct": "100"}],
            "account_id": ACC,
        },
    )
    env.put(STMT, statement([("10/09/2026", "APLICACAO CDB", "100.00")]))
    env.scan()
    (line,) = env.staged(STMT)
    assert line.review and line.review.suggestions[0].type == "link_investment"
    env.confirm_all(STMT)
    (mov,) = env.repo.get("investments", inv.id).movements
    assert mov.origin.type == "import" and mov.type == "contribution"

    data = (env.inbox / STMT).read_bytes()
    env.rm(STMT)
    env.scan()
    (mov,) = env.repo.get("investments", inv.id).movements
    assert mov.origin.type == "manual" and "origem removida" in mov.warnings

    env.put(STMT, data)
    env.scan()
    (mov,) = env.repo.get("investments", inv.id).movements
    assert mov.origin.type == "import" and mov.warnings == []
    env.confirm_all(STMT)
    assert len(env.repo.get("investments", inv.id).movements) == 1


def test_r3_13_paid_invoice_link_cleared(env: Env) -> None:
    env.put(OCT, inter_invoice([Line(1, 9, 2026, "MERCADO A", "15.50")], amount_due="15,50"))
    env.scan()
    env.put(
        "extratos/conta/2026-10.pdf",
        statement(
            [("14/10/2026", "PAGAMENTO FATURA INTER", "15.50")],
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    env.scan()
    (pay,) = env.staged("extratos/conta/2026-10.pdf")
    assert pay.review and pay.review.suggestions[0].type == "invoice_payment"
    env.confirm_all("extratos/conta/2026-10.pdf")
    assert env.entry(OCT).paid_by_fingerprints == [pay.fingerprint]

    env.rm("extratos/conta/2026-10.pdf")
    env.scan()
    assert env.entry(OCT).paid_by_fingerprints == []


def test_r3_13_subscription_link_goes_but_subscription_stays(env: Env) -> None:
    Catalog(env.repo).create(
        "subscriptions",
        {
            "id": "sub_stream",
            "description": "STREAMING PLUS",
            "amount": "39.90",
            "card_id": INTER,
            "category_id": CAT,
            "start_month": "2026-01",
        },
    )
    env.put(OCT, inter((7, "STREAMING PLUS", "39.90")))
    env.scan()
    (line,) = env.staged(OCT)
    assert line.review and line.review.suggestions[0].type == "link_subscription"
    env.confirm_all(OCT)
    assert env.confirmed(OCT)[0].links.subscription_id == "sub_stream"
    env.rm(OCT)
    env.scan()
    assert env.repo.get("subscriptions", "sub_stream") is not None
    assert env.confirmed() == []


def test_r3_13_annotation_kept_when_line_removed_by_change(env: Env) -> None:
    env.put(OCT, inter((1, "MERCADO A", "10.00"), (2, "PADARIA B", "5.50")))
    env.scan()
    padaria = next(t for t in env.staged(OCT) if t.description == "PADARIA B")
    from expense_tracker.review.actions import edit_staged

    edit_staged(env.repo, padaria.id, {"note": "pão"}, env.clock.now())
    env.put(OCT, inter((1, "MERCADO A", "10.00")))
    env.scan()
    assert env.repo.get("annotations", padaria.fingerprint).note == "pão"


# ---------------------------------------------------------------- remove_lines (unit)


NOW = datetime(2026, 10, 12, 10, 0)


def _tx(fp: str, sha: str = "a" * 64, review: bool = False, **kw: object) -> Transaction:
    from expense_tracker.domain.models import ReviewInfo

    data: dict[str, object] = {
        "id": f"tx_{fp}",
        "fingerprint": fp,
        "source": Source(type="import", sha256=sha, path="faturas/x.pdf"),
        "card_id": INTER,
        "purchase_date": date(2026, 9, 1),
        "invoice_month": "2026-10",
        "description": f"LINE {fp}",
        "amount": Decimal("10.00"),
        "review": ReviewInfo() if review else None,
    }
    data.update(kw)
    return Transaction.model_validate(data)


def _plan(pid: str, **kw: object) -> InstallmentPlan:
    data: dict[str, object] = {
        "id": pid,
        "card_id": INTER,
        "description": "Plano",
        "total_installments": 3,
        "first_invoice_month": "2026-10",
        "total_amount": Decimal("30.00"),
    }
    data.update(kw)
    return InstallmentPlan.model_validate(data)


def test_r3_13_remove_lines_with_no_fingerprints_is_noop(env: Env) -> None:
    env.repo.put("transactions", _tx("fp1"))
    assert remove_lines(env.repo, set(), NOW) == []
    assert env.repo.get("transactions", "tx_fp1") is not None


def test_r3_13_fingerprint_still_in_other_document_keeps_derived(env: Env) -> None:
    env.repo.put("transactions", _tx("fp1", sha="a" * 64))
    env.repo.put("staging", _tx("fp1", sha="b" * 64, review=True))
    env.repo.put(
        "installment_plans", _plan("plan_1", origin=Origin(type="import", fingerprint="fp1"))
    )
    notices = remove_lines(env.repo, {"fp1"}, NOW, sha="a" * 64)
    assert notices == []
    assert env.repo.get("transactions", "tx_fp1") is None
    assert env.repo.get("staging", "tx_fp1") is not None
    assert env.repo.get("installment_plans", "plan_1") is not None


def test_r3_13_anticipation_fingerprint_removed_from_list(env: Env) -> None:
    env.repo.put("transactions", _tx("fp1"))
    env.repo.put("transactions", _tx("fp2", amount=Decimal("25.00")))
    env.repo.put(
        "installment_plans",
        _plan(
            "plan_m",
            anticipation=Anticipation(
                from_n=2,
                target_month="2026-10",
                amount=Decimal("35.00"),
                linked_fingerprints=["fp1", "fp2"],
            ),
        ),
    )
    remove_lines(env.repo, {"fp1"}, NOW)
    ant = env.repo.get("installment_plans", "plan_m").anticipation
    assert ant.linked_fingerprints == ["fp2"] and ant.amount == Decimal("25.00")

    remove_lines(env.repo, {"fp2"}, NOW)
    ant = env.repo.get("installment_plans", "plan_m").anticipation
    # empty list: the anticipation is back to "forecast" (kept, can be undone, R7.4)
    assert ant is not None and ant.linked_fingerprints == [] and ant.amount is None


def test_r3_13_import_plan_anticipated_by_its_own_line_is_dropped(env: Env) -> None:
    env.repo.put("transactions", _tx("fp1"))
    env.repo.put(
        "installment_plans",
        _plan(
            "plan_i",
            origin=Origin(type="import", fingerprint="fp1"),
            anticipation=Anticipation(
                from_n=2, target_month="2026-10", linked_fingerprints=["fp1"]
            ),
        ),
    )
    notices = remove_lines(env.repo, {"fp1"}, NOW)
    assert env.repo.get("installment_plans", "plan_i") is None
    assert notices == ["plan plan_i removed"]


def test_r3_13_plan_with_status_override_or_manual_anticipation_kept_as_manual(env: Env) -> None:
    from expense_tracker.domain.models import StatusOverride

    env.repo.put("transactions", _tx("fp1"))
    env.repo.put("transactions", _tx("fp2"))
    env.repo.put(
        "installment_plans",
        _plan(
            "plan_c",
            origin=Origin(type="import", fingerprint="fp1"),
            status_override=StatusOverride(from_n=2),
        ),
    )
    env.repo.put(
        "installment_plans",
        _plan(
            "plan_a",
            origin=Origin(type="import", fingerprint="fp2"),
            anticipation=Anticipation(from_n=2, target_month="2026-11", amount=Decimal("20.00")),
        ),
    )
    remove_lines(env.repo, {"fp1", "fp2"}, NOW)
    for pid in ("plan_c", "plan_a"):
        plan = env.repo.get("installment_plans", pid)
        assert plan.origin.type == "manual" and "origem removida" in plan.warnings


def test_r3_13_internal_transfer_link_cleared(env: Env) -> None:
    env.repo.put("transactions", _tx("fp1", account_id=ACC, card_id=None, payment_method="pix"))
    env.repo.put(
        "transactions",
        _tx(
            "fp2",
            account_id=ACC,
            card_id=None,
            payment_method="pix",
            links=Links(internal_transfer_fingerprint="fp1"),
        ),
    )
    remove_lines(env.repo, {"fp1"}, NOW)
    assert env.repo.get("transactions", "tx_fp2").links.internal_transfer_fingerprint is None


def test_r3_13_unrelated_derived_objects_untouched(env: Env) -> None:
    env.repo.put("transactions", _tx("fp1"))
    env.repo.put(
        "transactions",
        _tx("fp9", installment=InstallmentRef(plan_id="plan_x", n=1, of=3)),
    )
    env.repo.put(
        "installment_plans", _plan("plan_x", origin=Origin(type="import", fingerprint="fp9"))
    )
    remove_lines(env.repo, {"fp1"}, NOW)
    assert env.repo.get("installment_plans", "plan_x") == _plan(
        "plan_x", origin=Origin(type="import", fingerprint="fp9")
    )


def test_r3_13_relink_on_return_only_touches_matching_fingerprints(env: Env) -> None:
    from expense_tracker.domain.models import Investment, Movement, Settlement

    env.repo.put(
        "settlements",
        Settlement(
            id="set_a",
            origin=Origin(type="manual", fingerprint="fp1"),
            from_user_id=OTHER,
            to_user_id=ME,
            amount=Decimal("1.00"),
            date=date(2026, 9, 1),
            month="2026-09",
            warnings=["origem removida", "outro"],
        ),
    )
    env.repo.put(
        "investments",
        Investment(
            id="inv_a",
            name="X",
            owners=[Share(user_id=ME, pct=Decimal("100"))],
            movements=[
                Movement(
                    date=date(2026, 9, 1),
                    type="contribution",
                    amount=Decimal("1.00"),
                    origin=Origin(type="manual", fingerprint="fp_other"),
                )
            ],
        ),
    )
    relink_on_return(env.repo, {"fp1"})
    st = env.repo.get("settlements", "set_a")
    assert st.origin.type == "import" and st.warnings == ["outro"]
    assert env.repo.get("investments", "inv_a").movements[0].origin.type == "manual"


def test_r3_3_move_lines_moves_only_kept_fingerprints(env: Env) -> None:
    env.repo.put("transactions", _tx("fp1"))
    env.repo.put("staging", _tx("fp2", review=True))
    env.repo.put("staging", _tx("fp3", review=True))
    new = ManifestEntry(path="faturas/novo.pdf", sha256="c" * 64, size=1, mtime=NOW, kind="fatura")
    move_lines(env.repo, "a" * 64, new, {"fp1", "fp2"})
    assert env.repo.get("transactions", "tx_fp1").source.sha256 == "c" * 64
    assert env.repo.get("staging", "tx_fp2").source.path == "faturas/novo.pdf"
    assert env.repo.get("staging", "tx_fp3").source.sha256 == "a" * 64


def test_r3_10_refresh_status_ignores_unknown_or_inactive_sha(env: Env) -> None:
    refresh_status(env.repo, "z" * 64)  # no entry: nothing happens
    entry = ManifestEntry(
        path="faturas/x.pdf", sha256="a" * 64, size=1, mtime=NOW, kind="fatura", status="error"
    )
    env.repo.put("import_manifest", entry)
    env.repo.put("staging", _tx("fp1", review=True))
    refresh_status(env.repo, "a" * 64)
    assert env.repo.get("import_manifest", "faturas/x.pdf").status == "error"


def test_r3_10_refresh_status_transitions(env: Env) -> None:
    sha = "a" * 64
    entry = ManifestEntry(path="faturas/x.pdf", sha256=sha, size=1, mtime=NOW, kind="fatura")
    env.repo.put("import_manifest", entry.model_copy(update={"status": "confirmed"}))
    env.repo.put("staging", _tx("fp1", review=True))
    refresh_status(env.repo, sha)
    assert env.repo.get("import_manifest", entry.path).status == "pending_review"
    env.repo.put("transactions", _tx("fp2"))
    refresh_status(env.repo, sha)
    assert env.repo.get("import_manifest", entry.path).status == "partially_confirmed"
    env.repo.delete("staging", "tx_fp1")
    refresh_status(env.repo, sha)
    assert env.repo.get("import_manifest", entry.path).status == "confirmed"
    env.repo.put(
        "import_manifest",
        env.repo.get("import_manifest", entry.path).model_copy(
            update={"supersedes_candidate": "faturas/a.pdf"}
        ),
    )
    refresh_status(env.repo, sha)
    assert env.repo.get("import_manifest", entry.path).status == "pending_review"
