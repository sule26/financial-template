"""End-to-end scenarios of docs/11 "Cenários" (and docs/09 "Por que não há dupla contagem").

Real pipeline: synthetic files in ``inbox/`` → SyncEngine → staging (reconciliation) → Confirmer →
Reports / Ledger. No HTTP.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from typing import Any

import pytest

from conftest import ANA, FOOD, HOME, ME, PAI, TECH, World
from expense_tracker.domain.models import Kind, Share, SplitRef
from expense_tracker.review.actions import edit_staged, reconcile_manual
from expense_tracker.review.confirm import ReviewError
from expense_tracker.review.fingerprint import derived_id
from fixtures.files import STATEMENT_PROFILE, Line, inter_invoice, nubank_invoice, statement

OCT = "2026-10"


@pytest.fixture
def w(world: World) -> World:
    world.base()
    world.categorize_all(FOOD)
    return world


def inter(w: World, lines: list[Line], month: str = OCT, name: str | None = None, **kw: Any) -> str:
    y, m = month.split("-")
    rel = f"faturas/{name or 'inter-' + month}.pdf"
    return w.drop(rel, inter_invoice(lines, due=f"15/{m}/{y}", **kw))


def suggestion_types(w: World, rel: str) -> dict[str, list[str]]:
    return {
        t.description: [s.type for s in (t.review.suggestions if t.review else [])]
        for t in w.staged(rel)
    }


def plan_x(w: World, **extra: Any) -> None:
    """Existing plan: 10 × 50.00 from 2026-08 (installment 3 is due in 2026-10)."""
    data = {
        "id": "plan_x",
        "card_id": "card_inter",
        "description": "LOJA X",
        "total_installments": 10,
        "first_invoice_month": "2026-08",
        "total_amount": "500.00",
        "category_id": TECH,
    }
    data.update(extra)
    w.catalog.create("installment_plans", data)


def tx_by_desc(w: World, text: str) -> Any:
    found = [t for t in w.confirmed() if text in t.description]
    assert len(found) == 1, [t.description for t in w.confirmed()]
    return found[0]


# ================================================================== installments (R8.1, R8.2)


def test_r8_1_installment_3_of_10_of_existing_plan(w: World) -> None:
    plan_x(w)
    assert w.projection()[OCT] == D("50.00")  # projected before the invoice
    rel = inter(
        w,
        [
            Line(3, 8, 2026, "LOJA X (Parcela 3 de 10)", "50.00"),
            Line(20, 9, 2026, "MERCADO BOM", "100.00"),
        ],
    )
    assert suggestion_types(w, rel)["LOJA X (Parcela 3 de 10)"] == ["link_plan"]
    w.confirm(rel)
    assert [p.id for p in w.repo.all("installment_plans")] == ["plan_x"]  # no new purchase
    loja = tx_by_desc(w, "LOJA X")
    assert loja.installment.plan_id == "plan_x"
    assert (loja.category_id, loja.allocation_origin) == (TECH, "owners:card")
    assert w.month_total(OCT) == D("150.00")  # month total = invoice
    assert w.entry(rel).warnings == []
    assert w.projection()["2026-11"] == D("50.00")  # the plan keeps projecting


def test_r8_2_installment_1_of_10_without_plan_creates_it_and_projects_9(w: World) -> None:
    rel = inter(w, [Line(20, 9, 2026, "LOJA NOVA (Parcela 1 de 10)", "80.00")])
    w.confirm(rel)
    [plan] = w.repo.all("installment_plans")
    tx = tx_by_desc(w, "LOJA NOVA")
    assert plan.id == derived_id("plan", tx.fingerprint)
    assert (plan.origin.type, plan.origin.fingerprint) == ("import", tx.fingerprint)
    assert (plan.first_invoice_month, plan.total_installments) == (OCT, 10)
    assert tx.installment.plan_id == plan.id
    proj = w.projection()
    assert proj[OCT] == D("80.00")
    future = [m for m, v in proj.items() if m > OCT and v == D("80.00")]
    assert future == [f"2026-{m}" for m in ("11", "12")] + [f"2027-0{m}" for m in range(1, 8)]
    assert proj["2027-08"] == D("0.00")


def test_r3_13_removing_the_invoice_that_created_the_plan(w: World) -> None:
    lines = [Line(20, 9, 2026, "LOJA NOVA (Parcela 1 de 10)", "80.00")]
    rel = inter(w, lines)
    w.confirm(rel)
    [plan] = w.repo.all("installment_plans")
    w.remove(rel)
    assert w.repo.all("installment_plans") == []
    assert w.projection()["2026-11"] == D("0.00")
    rel = inter(w, lines)  # put it back
    w.confirm(rel)
    assert [p.id for p in w.repo.all("installment_plans")] == [plan.id]
    assert w.projection()["2026-11"] == D("80.00")


# ================================================================== anticipation (R7.3, R7.5, 7b)


def ant_plan(w: World, **extra: Any) -> None:
    """Plan 10 × 30.00 from 2026-02 with anticipation of 9–10 registered for 2026-10."""
    data = {
        "id": "plan_y",
        "card_id": "card_nu",
        "description": "Loja Y",
        "total_installments": 10,
        "first_invoice_month": "2026-02",
        "total_amount": "300.00",
        "category_id": TECH,
        "anticipation": {"from_n": 9, "target_month": OCT},
    }
    data.update(extra)
    w.catalog.create("installment_plans", data)


def nu(w: World, lines: list[Line], name: str = "nu-2026-10", **kw: Any) -> str:
    return w.drop(f"faturas/{name}.pdf", nubank_invoice(lines, **kw))


def test_r7_3_registered_anticipation_and_invoice_with_the_installments(w: World) -> None:
    w.nubank()
    ant_plan(w)
    assert w.projection()[OCT] == D("60.00")  # forecast of the anticipation
    rel = nu(
        w,
        [
            Line(15, 9, 2026, "Loja Y - Parcela 9/10", "30.00", card=""),
            Line(15, 9, 2026, "Loja Y - Parcela 10/10", "30.00", card=""),
        ],
    )
    w.confirm(rel)
    plan = w.repo.get("installment_plans", "plan_y")
    assert len(w.repo.all("installment_plans")) == 1  # no new plan
    lines = sorted(w.confirmed(), key=lambda t: t.installment.n)
    assert plan.anticipation.linked_fingerprints == [t.fingerprint for t in lines]
    assert plan.anticipation.amount == D("60.00")  # real value recorded
    assert all(t.links.anticipation_plan_id == "plan_y" for t in lines)
    assert w.month_total(OCT) == D("60.00")  # no duplication
    proj = w.projection()
    assert proj["2026-11"] == proj["2026-12"] == D("0.00")  # following months empty


def test_r7_3_anticipation_with_discounted_values_does_not_create_a_plan(w: World) -> None:
    w.nubank()
    ant_plan(w)
    rel = nu(
        w,
        [
            Line(15, 9, 2026, "Antecipada - Loja Y - Parcela 9/10", "28.50", card=""),
            Line(15, 9, 2026, "Antecipada - Loja Y - Parcela 10/10", "28.50", card=""),
        ],
    )
    w.confirm(rel)
    assert [p.id for p in w.repo.all("installment_plans")] == ["plan_y"]
    assert w.repo.get("installment_plans", "plan_y").anticipation.amount == D("57.00")


def test_r7_5_anticipation_with_discount_on_a_separate_line(w: World) -> None:
    w.nubank()
    half = [{"user_id": ME, "pct": "50"}, {"user_id": ANA, "pct": "50"}]
    ant_plan(w, allocations=half)
    rel = nu(
        w,
        [
            Line(15, 9, 2026, "Antecipada - Loja Y - Parcela 9/10", "30.00", card=""),
            Line(15, 9, 2026, "Antecipada - Loja Y - Parcela 10/10", "30.00", card=""),
            Line(15, 9, 2026, "Desconto Antecipação Loja Y", "-5.00", card=""),
        ],
        amount_due="55,00",
    )
    discount = w.staged_by_desc("Desconto", rel)
    # the discount inherits the plan's division already in Review (level 2)
    assert discount.allocation_origin == "plan:plan_y"
    w.confirm(rel)
    plan = w.repo.get("installment_plans", "plan_y")
    assert plan.anticipation.amount == D("55.00")  # charges − discount
    assert len(plan.anticipation.linked_fingerprints) == 3
    disc = tx_by_desc(w, "Desconto")
    assert disc.amount == D("-5.00")
    assert disc.allocations == [Share(user_id=ME, pct=D("50")), Share(user_id=ANA, pct=D("50"))]
    assert disc.links.anticipation_plan_id == "plan_y"
    assert w.month_total(OCT) == D("55.00")
    balances = w.reports().balances(ME, False)
    assert balances["people"][0]["net"] == "27.50"  # Ana owes half of the real 55.00


def test_r8_8_two_installments_of_the_same_plan_in_one_invoice(w: World) -> None:
    rel = inter(
        w,
        [
            Line(1, 2, 2026, "LOJA Z (Parcela 9 de 10)", "30.00"),
            Line(1, 2, 2026, "LOJA Z (Parcela 10 de 10)", "30.00"),
        ],
    )
    types = suggestion_types(w, rel)
    assert types["LOJA Z (Parcela 10 de 10)"] == ["bank_anticipation"]
    w.confirm(rel)
    [plan] = w.repo.all("installment_plans")
    assert plan.first_invoice_month == "2026-02"
    assert (plan.anticipation.from_n, plan.anticipation.target_month) == (10, OCT)
    ten = tx_by_desc(w, "Parcela 10")
    assert plan.anticipation.linked_fingerprints == [ten.fingerprint]
    assert plan.anticipation.amount == D("30.00")
    assert w.month_total(OCT) == D("60.00")
    assert w.projection()["2026-11"] == D("0.00")


def test_r8_8_two_installments_of_existing_plan_create_bank_anticipation(w: World) -> None:
    plan_x(w)
    rel = inter(
        w,
        [
            Line(3, 8, 2026, "LOJA X (Parcela 3 de 10)", "50.00"),
            Line(3, 8, 2026, "LOJA X (Parcela 4 de 10)", "50.00"),
        ],
    )
    assert w.entry(rel).warnings == []
    w.confirm(rel)
    plan = w.repo.get("installment_plans", "plan_x")
    assert (plan.anticipation.from_n, plan.anticipation.target_month) == (4, OCT)
    assert plan.anticipation.amount == D("50.00")
    assert w.month_total(OCT) == D("100.00")


def test_r8_8_missing_expected_installment_warns(w: World) -> None:
    plan_x(w)
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "100.00")])
    assert w.entry(rel).warnings == ["expected_installment_missing:plan_x:3"]


def test_r8_8_answer_anticipated_at_the_bank_creates_the_anticipation(w: World) -> None:
    # docs/09 row 7: "antecipada no banco" removes n..N from the projection (no H restriction)
    plan_x(w)
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "100.00")])
    plan = w.txs.anticipated_at_bank("plan_x", from_n=3)
    assert plan.status_override.status == "anticipated_at_bank"
    assert plan.status_override.from_n == 3
    w.confirm(rel)
    assert w.month_total(OCT) == D("100.00")
    assert w.projection()["2026-11"] == D("0.00")


def test_r8_8_answer_cancelled_sets_status_override(w: World) -> None:
    plan_x(w)
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "100.00")])
    plan = w.txs.cancel_plan("plan_x", from_n=3)
    assert plan.status_override.from_n == 3
    w.confirm(rel)
    assert w.month_total(OCT) == D("100.00")
    assert w.projection()["2026-11"] == D("0.00")


# ================================================================== refund (R8.7)


def test_r8_7_refund_of_installment_purchase(w: World) -> None:
    plan_x(w)
    rel = inter(
        w,
        [
            Line(3, 8, 2026, "LOJA X (Parcela 3 de 10)", "50.00"),
            Line(25, 9, 2026, "LOJA X", "-350.00"),
        ],
    )
    refund = next(t for t in w.staged(rel) if t.amount < 0)
    s = refund.review.suggestions[0]
    assert (s.type, s.target_id, s.data["cancel_suggested"]) == ("refund_plan", "plan_x", True)
    w.confirm(rel)
    assert [p.id for p in w.repo.all("installment_plans")] == ["plan_x"]  # no new plan
    tx = next(t for t in w.confirmed() if t.amount < 0)
    assert (tx.kind, tx.amount, tx.installment.plan_id) == (Kind.REFUND, D("-350.00"), "plan_x")
    assert tx.category_id == TECH  # division/category of the plan
    assert w.month_total(OCT) == D("-300.00")


def test_r8_7_refund_with_installment_and_no_plan_never_creates_a_plan(w: World) -> None:
    rel = inter(w, [Line(25, 9, 2026, "LOJA SEM PLANO (Parcela 1 de 3)", "-30.00")])
    w.confirm(rel)
    assert w.repo.all("installment_plans") == []


# ================================================================== subscription (R8.3)


def test_r8_3_forecast_subscription_and_charge_count_once(w: World) -> None:
    w.catalog.create(
        "subscriptions",
        {
            "id": "sub_s",
            "description": "STREAMING",
            "amount": "40.00",
            "card_id": "card_inter",
            "start_month": "2026-01",
            "category_id": HOME,
        },
    )
    assert w.projection()[OCT] == D("40.00")
    rel = inter(w, [Line(1, 10, 2026, "STREAMING", "40.00")])
    w.confirm(rel)
    tx = tx_by_desc(w, "STREAMING")
    assert tx.links.subscription_id == "sub_s"
    assert tx.category_id == HOME
    assert w.month_total(OCT) == D("40.00")
    assert w.projection()["2026-11"] == D("40.00")


# ================================================================== manual entries (R8.6, R10.3)


def test_r8_6_r10_3_manual_on_card_and_same_purchase_on_invoice(w: World) -> None:
    half = [{"user_id": ME, "pct": "50"}, {"user_id": ANA, "pct": "50"}]
    res = w.manual(
        purchase_date=date(2026, 9, 20),
        amount="100.00",
        description="Mercado Bom",
        category_id=HOME,
        card_id="card_inter",
        allocations=half,
        note="churrasco",
    )
    manual_id = res["transaction"]["id"]
    assert res["reconciliation"] == {"status": "projected"}
    lone = w.manual(
        purchase_date=date(2026, 9, 25),
        amount="15.00",
        description="Padaria",
        category_id=FOOD,
        card_id="card_inter",
    )["transaction"]["id"]
    assert w.month_total(OCT) == D("115.00")  # provisional, month still projected
    rel = inter(
        w, [Line(20, 9, 2026, "MERCADO BOM", "100.00"), Line(22, 9, 2026, "FARMACIA", "30.00")]
    )
    assert w.entry(rel).warnings == [f"unmatched_manual:{lone}"]
    line = w.staged_by_desc("MERCADO", rel)
    assert [s.type for s in line.review.suggestions] == ["match_manual"]
    assert line.category_id == HOME  # the manual's edits are offered already in Review
    w.confirm(rel)
    assert w.repo.get("transactions", manual_id) is None  # absorbed
    tx = tx_by_desc(w, "MERCADO")
    ann = w.repo.get("annotations", tx.fingerprint)
    assert (ann.category_id, ann.note) == (HOME, "churrasco")
    assert ann.allocations == [Share(user_id=ME, pct=D("50")), Share(user_id=ANA, pct=D("50"))]
    assert tx.category_id == HOME
    # counted once; the unmatched manual no longer counts in a real month
    assert w.month_total(OCT) == D("130.00")
    assert w.repo.get("transactions", lone) is not None


def test_r10_3_retroactive_manual_in_month_with_document(w: World) -> None:
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "100.00")])
    w.confirm(rel)
    res = w.manual(
        purchase_date=date(2026, 9, 20),
        amount="100.00",
        description="Mercado Bom",
        category_id=HOME,
        card_id="card_inter",
        note="festa",
    )
    rec = res["reconciliation"]
    tx = tx_by_desc(w, "MERCADO")
    assert rec["status"] == "absorbed"
    assert (rec["into"], rec["document"]) == (tx.id, rel)
    assert w.repo.get("transactions", res["transaction"]["id"]) is None
    assert w.repo.get("annotations", tx.fingerprint).note == "festa"
    assert w.month_total(OCT) == D("100.00")
    other = w.manual(
        purchase_date=date(2026, 9, 21),
        amount="12.00",
        description="Sorvete",
        category_id=FOOD,
        card_id="card_inter",
    )["reconciliation"]
    assert other["status"] == "not_in_document"
    assert other["document"] == rel


def test_r10_3_retroactive_manual_on_staged_document_is_absorbed(w: World) -> None:
    w.repo.delete("rules", w.repo.all("rules")[0].id)
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "100.00")])
    res = w.manual(
        purchase_date=date(2026, 9, 20),
        amount="100.00",
        description="Mercado Bom",
        category_id=HOME,
        card_id="card_inter",
    )
    assert res["reconciliation"]["status"] == "absorbed"
    staged = w.staged_by_desc("MERCADO", rel)
    assert staged.category_id == HOME
    assert w.repo.get("annotations", staged.fingerprint).category_id == HOME


def test_r10_3_manual_on_statement_account(w: World) -> None:
    res = w.manual(
        purchase_date=date(2026, 10, 7),
        amount="10.00",
        description="Padaria",
        category_id=FOOD,
        account_id="acc_me",
        payment_method="pix",
    )
    assert res["reconciliation"] == {"status": "projected"}
    rel = w.drop(
        "extratos/conta-10.pdf",
        statement(
            [("07/10/2026", "PIX ENVIADO PADARIA", "10.00")], period=("01/10/2026", "31/10/2026")
        ),
    )
    assert suggestion_types(w, rel)["PIX ENVIADO PADARIA"] == ["match_manual"]
    w.confirm(rel)
    assert w.repo.get("transactions", res["transaction"]["id"]) is None
    late = w.manual(
        purchase_date=date(2026, 10, 8),
        amount="99.00",
        description="Livro",
        category_id=FOOD,
        account_id="acc_me",
        payment_method="pix",
    )
    assert late["reconciliation"]["status"] == "not_in_document"


# ================================================================== statement rows 12–15


def test_r8_4_invoice_and_statement_with_its_payment(w: World) -> None:
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "130.00")], amount_due="130,00")
    w.confirm(rel)
    srel = w.drop(
        "extratos/conta-10.pdf",
        statement(
            [("14/10/2026", "PAGAMENTO FATURA INTER", "130.00")],
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    w.confirm(srel)
    pay = tx_by_desc(w, "PAGAMENTO")
    assert pay.kind is Kind.TRANSFER
    assert pay.category_id is None
    assert (pay.links.paid_invoice.card_id, pay.links.paid_invoice.invoice_month) == (
        "card_inter",
        OCT,
    )
    assert w.entry(rel).paid_by_fingerprints == [pay.fingerprint]
    assert w.month_total(OCT) == D("130.00")  # spending counted once


def test_r8_4_removing_the_statement_unmarks_the_invoice(w: World) -> None:
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "130.00")], amount_due="130,00")
    srel = w.drop(
        "extratos/conta-10.pdf",
        statement(
            [("14/10/2026", "PAGAMENTO FATURA INTER", "130.00")],
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    w.confirm(srel)
    assert w.entry(rel).paid_by_fingerprints
    w.remove(srel)
    assert w.entry(rel).paid_by_fingerprints == []


def joint_account(w: World, profile: str = "banco-teste-extrato") -> None:
    w.catalog.create(
        "accounts",
        {
            "id": "acc_joint",
            "name": "Conjunta",
            "profile_id": profile,
            "account_hint": "99999-0",
            "owners": [{"user_id": ME, "pct": "50"}, {"user_id": ANA, "pct": "50"}],
            "responsible_user_id": ME,
        },
    )


def test_r8_10_pix_from_my_account_to_the_joint_account(w: World) -> None:
    joint_account(w)
    a = w.drop(
        "extratos/me.pdf",
        statement(
            [("07/10/2026", "PIX ENVIADO CONTA CONJUNTA", "300.00")],
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    b = w.drop(
        "extratos/joint.pdf",
        statement(
            [("07/10/2026", "PIX RECEBIDO FULANO", "-300.00")],
            account="99999-0",
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    w.confirm(a)
    w.confirm(b)
    assert {t.kind for t in w.confirmed()} == {Kind.TRANSFER}


def test_r8_10_transfer_between_my_accounts_both_become_transfer(w: World) -> None:
    # a profile that classifies TEDs as transfers keeps the sign (out > 0, in < 0)
    profile = STATEMENT_PROFILE.replace(
        "  - {match: 'TARIFA', kind: fee}",
        "  - {match: 'TARIFA', kind: fee}\n  - {match: '^TED', kind: transfer}",
    )
    (w.settings.profiles_dir / "statement.yaml").write_text(profile, encoding="utf-8")
    joint_account(w)
    a = w.drop(
        "extratos/me.pdf",
        statement(
            [("07/10/2026", "TED CONTA CONJUNTA", "300.00")], period=("01/10/2026", "31/10/2026")
        ),
    )
    b = w.drop(
        "extratos/joint.pdf",
        statement(
            [("08/10/2026", "TED RECEBIDA", "-300.00")],
            account="99999-0",
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    assert suggestion_types(w, b)["TED RECEBIDA"] == ["internal_transfer"]
    w.confirm(a)
    w.confirm(b)
    out, inn = tx_by_desc(w, "TED CONTA"), tx_by_desc(w, "TED RECEBIDA")
    assert out.kind is inn.kind is Kind.TRANSFER
    assert out.links.internal_transfer_fingerprint == inn.fingerprint
    assert inn.links.internal_transfer_fingerprint == out.fingerprint
    assert w.month_total(OCT) == D("0.00")


def test_r8_10_transfer_confirmed_in_reverse_order(w: World) -> None:
    profile = STATEMENT_PROFILE.replace(
        "  - {match: 'TARIFA', kind: fee}",
        "  - {match: 'TARIFA', kind: fee}\n  - {match: '^TED', kind: transfer}",
    )
    (w.settings.profiles_dir / "statement.yaml").write_text(profile, encoding="utf-8")
    joint_account(w)
    a = w.drop(
        "extratos/me.pdf",
        statement(
            [("07/10/2026", "TED CONTA CONJUNTA", "300.00")], period=("01/10/2026", "31/10/2026")
        ),
    )
    b = w.drop(
        "extratos/joint.pdf",
        statement(
            [("08/10/2026", "TED RECEBIDA", "-300.00")],
            account="99999-0",
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    w.confirm(b)
    w.confirm(a)
    out = tx_by_desc(w, "TED CONTA")
    assert out.links.internal_transfer_fingerprint == tx_by_desc(w, "TED RECEBIDA").fingerprint


def test_r6_6_pix_from_parents_is_a_settlement_not_income(w: World) -> None:
    rel = w.drop(
        "extratos/conta-10.pdf",
        statement(
            [("05/10/2026", "PIX RECEBIDO JOSE DA SILVA", "-200.00")],
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    w.confirm(rel)
    tx = tx_by_desc(w, "JOSE")
    assert tx.kind is Kind.SETTLEMENT
    [st] = w.repo.all("settlements")
    assert st.id == tx.links.settlement_id == derived_id("set", tx.fingerprint)
    assert (st.from_user_id, st.to_user_id, st.amount, st.month) == (PAI, ME, D("200.00"), OCT)
    assert st.origin.fingerprint == tx.fingerprint
    summary = w.reports().summary(OCT, ME, False)
    assert summary["series"][-1]["income"] is None  # not counted as income
    assert w.month_total(OCT) == D("0.00")
    # removing the statement keeps the settlement as manual ("origem removida")
    w.remove(rel)
    [st] = w.repo.all("settlements")
    assert st.origin.type == "manual"
    assert "origem removida" in st.warnings


def test_r9_4_investment_contribution_on_statement(w: World) -> None:
    w.catalog.create(
        "investments",
        {
            "id": "inv_cdb",
            "name": "CDB",
            "owners": [{"user_id": ME, "pct": "100"}],
            "account_id": "acc_me",
        },
    )
    rel = w.drop(
        "extratos/conta-10.pdf",
        statement(
            [("06/10/2026", "APLICACAO CDB", "300.00"), ("20/10/2026", "RESGATE CDB", "-100.00")],
            period=("01/10/2026", "31/10/2026"),
        ),
    )
    w.confirm(rel)
    for t in w.confirmed():
        assert t.kind is Kind.TRANSFER
        assert t.links.investment_id == "inv_cdb"
    inv = w.repo.get("investments", "inv_cdb")
    assert [(m.type, m.amount) for m in inv.movements] == [
        ("contribution", D("300.00")),
        ("withdrawal", D("100.00")),
    ]
    assert all(m.origin.type == "import" for m in inv.movements)
    assert w.month_total(OCT) == D("0.00")  # not spending


# ================================================================== ownership (R6)


def test_r6_2_joint_account_card_is_split_50_50(w: World) -> None:
    joint_account(w)
    w.nubank(owners=None, responsible_user_id=None, account_id="acc_joint")
    rel = nu(w, [Line(12, 9, 2026, "Supermercado", "100.00", card="")])
    line = w.staged_by_desc("Supermercado", rel)
    assert line.allocation_origin == "owners:account"
    w.confirm(rel)
    tx = tx_by_desc(w, "Supermercado")
    assert tx.allocations == [Share(user_id=ME, pct=D("50")), Share(user_id=ANA, pct=D("50"))]
    people = w.reports().balances(ME, False)["people"]
    assert [(p["user_id"], p["net"]) for p in people] == [(ANA, "50.00")]  # Ana owes me


def test_r6_9_additional_card_with_its_own_section(w: World) -> None:
    w.catalog.create(
        "cards",
        {
            "id": "card_add",
            "name": "Adicional Ana",
            "parent_card_id": "card_inter",
            "owners": [{"user_id": ANA, "pct": "100"}],
            "responsible_user_id": ANA,
            "last_digits": ["9999"],
        },
    )
    rel = inter(
        w,
        [
            Line(20, 9, 2026, "MERCADO BOM", "100.00", card="5678"),
            Line(21, 9, 2026, "LIVRARIA", "40.00", card="9999"),
        ],
    )
    assert len(w.repo.all("import_manifest")) == 1  # a single document
    w.confirm(rel)
    book = tx_by_desc(w, "LIVRARIA")
    assert book.card_id == "card_add"
    assert (book.allocations, book.allocation_origin) == (
        [Share(user_id=ANA, pct=D("100"))],
        "owners:card",
    )
    assert tx_by_desc(w, "MERCADO").card_id == "card_inter"
    assert w.reports().summary(OCT, None, False)["by_card"] == {"card_inter": "140.00"}


def test_r6_11_split_casal_changes_from_60_40_to_55_45(w: World) -> None:
    w.catalog.create(
        "split_profiles",
        {
            "id": "split_casal",
            "name": "Casal",
            "members": [ME, ANA],
            "history": [
                {
                    "from_month": "2026-01",
                    "shares": [{"user_id": ME, "pct": "60"}, {"user_id": ANA, "pct": "40"}],
                },
                {
                    "from_month": "2026-11",
                    "shares": [{"user_id": ME, "pct": "55"}, {"user_id": ANA, "pct": "45"}],
                },
            ],
        },
    )
    w.rule("MERCADO", FOOD, priority=1, allocations={"split_id": "split_casal"})
    rel = inter(w, [Line(20, 9, 2026, "MERCADO BOM", "100.00")])
    w.confirm(rel)
    tx = tx_by_desc(w, "MERCADO")
    assert tx.allocations == SplitRef(split_id="split_casal")  # confirmation keeps the reference
    nov = w.manual(
        purchase_date=date(2026, 10, 20),
        amount="100.00",
        description="Mercado Bom",
        category_id=FOOD,
        card_id="card_inter",
        allocations={"split_id": "split_casal"},
    )["transaction"]
    assert nov["invoice_month"] == "2026-11"
    ledger = w.ledger()
    parts = {i.month: ledger.parts_of(i) for m in (OCT, "2026-11") for i in ledger.month(m).items}
    assert parts[OCT] == {ME: D("60.00"), ANA: D("40.00")}  # earlier month intact
    assert parts["2026-11"] == {ME: D("55.00"), ANA: D("45.00")}


# ================================================================== confirmation filter (R8.5)


def test_r8_5_invoice_only_in_review_keeps_month_projected(w: World) -> None:
    plan_x(w)
    inter(
        w,
        [
            Line(3, 8, 2026, "LOJA X (Parcela 3 de 10)", "50.00"),
            Line(20, 9, 2026, "MERCADO BOM", "100.00"),
        ],
    )
    confirmed_only = w.reports().summary(OCT, None, False)
    assert confirmed_only["total"] == "50.00"  # still projected, not zero
    assert confirmed_only["states"]["card_inter"] == "projected"
    with_pending = w.reports().summary(OCT, None, True)
    assert with_pending["total"] == "150.00"
    assert with_pending["states"]["card_inter"] == "real"


# ================================================================== recurring purchase (R12.3)


def test_r12_3_recurring_purchase_is_linked_and_reanchored(w: World) -> None:
    w.catalog.create(
        "recurring_purchases",
        {
            "id": "rec_racao",
            "description": "RACAO PET",
            "estimated_amount": "200.00",
            "every": {"value": 45},
            "last_date": "2026-08-01",
            "card_id": "card_inter",
            "category_id": HOME,
        },
    )
    assert w.projection()[OCT] == D("200.00")  # planned for 2026-09-15 → invoice of 2026-10
    rel = inter(w, [Line(20, 9, 2026, "RACAO PET SHOP", "210.00")])
    w.confirm(rel)
    tx = tx_by_desc(w, "RACAO")
    assert tx.links.recurring_purchase_id == "rec_racao"
    assert tx.category_id == HOME
    assert w.repo.get("recurring_purchases", "rec_racao").last_date == date(2026, 9, 20)
    assert w.month_total(OCT) == D("210.00")
    # next planned purchase 2026-11-04 (45 days after the real date) → invoice 2026-11
    assert w.projection()["2026-11"] == D("200.00")


# ================================================================== annotations (R5.4, R3.5)


def test_r5_4_rule_suggestion_after_same_edit_in_two_files(w: World) -> None:
    w.nubank()
    a = inter(w, [Line(20, 9, 2026, "PADARIA SOL", "10.00")])
    b = nu(w, [Line(12, 9, 2026, "Padaria Sol", "11.00", card="")])
    first = edit_staged(
        w.repo, w.staged_by_desc("PADARIA", a).id, {"category_id": HOME}, w.clock.now()
    )
    assert first["rule_suggestion"] is None
    second = edit_staged(
        w.repo, w.staged_by_desc("Padaria", b).id, {"category_id": HOME}, w.clock.now()
    )
    sug = second["rule_suggestion"]
    assert sug["description_regex"] == "PADARIA\\ SOL"
    assert sug["category_id"] == HOME
    assert sug["priority"] == 1010  # highest existing (1000) + 10
    # accepting creates the rule; it is not suggested again
    w.catalog.create(
        "rules",
        {
            "priority": sug["priority"],
            "when": {"description_regex": sug["description_regex"]},
            "then": {"category_id": HOME},
        },
    )
    again = edit_staged(
        w.repo, w.staged_by_desc("Padaria", b).id, {"category_id": HOME}, w.clock.now()
    )
    assert again["rule_suggestion"] is None


def test_r5_4_no_rule_suggestion_for_edits_in_the_same_file(w: World) -> None:
    a = inter(
        w, [Line(20, 9, 2026, "PADARIA SOL", "10.00"), Line(22, 9, 2026, "PADARIA SOL", "12.00")]
    )
    one, two = w.staged(a)
    edit_staged(w.repo, one.id, {"category_id": HOME}, w.clock.now())
    res = edit_staged(w.repo, two.id, {"category_id": HOME}, w.clock.now())
    assert res["rule_suggestion"] is None


def test_r5_4_same_resolved_division_in_two_files(w: World) -> None:
    w.nubank()
    w.catalog.create(
        "split_profiles",
        {
            "id": "split_casal",
            "name": "Casal",
            "members": [ME, ANA],
            "history": [
                {
                    "from_month": "2026-01",
                    "shares": [{"user_id": ME, "pct": "50"}, {"user_id": ANA, "pct": "50"}],
                }
            ],
        },
    )
    a = inter(w, [Line(20, 9, 2026, "PADARIA SOL", "10.00")])
    b = nu(w, [Line(12, 9, 2026, "Padaria Sol", "11.00", card="")])
    half = [Share(user_id=ME, pct=D("50")), Share(user_id=ANA, pct=D("50"))]
    edit_staged(w.repo, w.staged_by_desc("PADARIA", a).id, {"allocations": half}, w.clock.now())
    res = edit_staged(
        w.repo,
        w.staged_by_desc("Padaria", b).id,
        {"allocations": SplitRef(split_id="split_casal")},
        w.clock.now(),
    )
    sug = res["rule_suggestion"]
    assert sug["category_id"] is None
    assert sug["allocations"] == {"split_id": "split_casal"}


def test_r3_5_orphan_annotation_is_offered_on_reissued_invoice(w: World) -> None:
    a = inter(w, [Line(20, 9, 2026, "MERCADO BOM LTDA", "100.00")])
    edit_staged(
        w.repo, w.staged(a)[0].id, {"category_id": HOME, "note": "aniversário"}, w.clock.now()
    )
    w.confirm(a)
    old_fp = w.confirmed()[0].fingerprint
    w.remove(a)
    # the bank re-issued the invoice with a slightly different description
    b = inter(w, [Line(20, 9, 2026, "MERCADO BOM LTDX", "100.00")], name="inter-2026-10-v2")
    line = w.staged(b)[0]
    assert line.fingerprint != old_fp
    s = line.review.suggestions[0]
    assert (s.type, s.target_id) == ("apply_annotation", old_fp)
    w.confirm(b)
    tx = w.confirmed()[0]
    assert (tx.category_id, tx.note) == (HOME, "aniversário")
    assert w.repo.get("annotations", tx.fingerprint).category_id == HOME


def test_r3_5_edits_survive_removing_and_putting_back_the_invoice(w: World) -> None:
    lines = [Line(20, 9, 2026, "MERCADO BOM", "100.00")]
    a = inter(w, lines)
    alloc = [Share(user_id=ANA, pct=D("100"))]
    edit_staged(
        w.repo, w.staged(a)[0].id, {"category_id": HOME, "allocations": alloc}, w.clock.now()
    )
    w.confirm(a)
    w.remove(a)
    assert w.confirmed() == []
    a = inter(w, lines)
    line = w.staged(a)[0]
    assert (line.category_id, line.allocations, line.allocation_origin) == (HOME, alloc, "manual")


# ================================================================== confirmation (docs/09)


def test_r1_11_confirm_blocked_without_category(world: World) -> None:
    world.base()
    rel = inter(world, [Line(20, 9, 2026, "COISA NOVA", "10.00")])
    line = world.staged(rel)[0]
    assert line.review.warnings == ["category_missing"]
    with pytest.raises(ReviewError) as err:
        world.confirm(rel)
    assert err.value.code == "cannot_confirm"
    assert "category_missing" in str(err.value)
    res = edit_staged(world.repo, line.id, {"category_id": FOOD}, world.clock.now())
    assert res["transaction"]["review"]["warnings"] == []
    world.confirm(rel)
    assert world.entry(rel).status == "confirmed"


def test_r8_1_needs_choice_blocks_until_chosen(w: World) -> None:
    plan_x(w)
    plan_x(w, id="plan_x2", description="LOJA X.")
    rel = inter(w, [Line(3, 8, 2026, "LOJA X (Parcela 3 de 10)", "50.00")])
    line = w.staged(rel)[0]
    assert line.review.status == "needs_choice"
    with pytest.raises(ReviewError, match="needs_choice"):
        w.confirm(rel)
    with pytest.raises(ReviewError) as err:
        edit_staged(
            w.repo, line.id, {"choose": {"type": "choose_plan", "target_id": "nope"}}, w.clock.now()
        )
    assert err.value.code == "invalid_choice"
    res = edit_staged(
        w.repo, line.id, {"choose": {"type": "choose_plan", "target_id": "plan_x2"}}, w.clock.now()
    )
    assert res["transaction"]["review"]["status"] == "pending"
    w.confirm(rel)
    assert tx_by_desc(w, "LOJA X").installment.plan_id == "plan_x2"
    # the choice survives a re-import (annotation by fingerprint)
    assert w.repo.get("annotations", line.fingerprint).link_choices == {"choose_plan": "plan_x2"}


def overlapping(w: World) -> tuple[str, str]:
    a = w.drop(
        "extratos/set.pdf",
        statement(
            [("20/09/2026", "PIX ENVIADO PADARIA", "10.00")], period=("01/09/2026", "30/09/2026")
        ),
    )
    return a, "extratos/meio.pdf"


B_ROWS = [
    ("20/09/2026", "PIX ENVIADO PADARIA", "10.00"),
    ("05/10/2026", "PIX ENVIADO FEIRA", "20.00"),
]


def test_r3_12_overlapping_statements_count_once_and_overlap_is_not_confirmable(w: World) -> None:
    a, b_rel = overlapping(w)
    w.confirm(a)
    b = w.drop(b_rel, statement(B_ROWS, period=("15/09/2026", "15/10/2026")))
    dup = w.staged_by_desc("PADARIA", b)
    assert dup.review.status == "overlap"
    with pytest.raises(ReviewError, match="overlap"):
        w.confirmer().confirm([dup.id])
    w.confirmer().confirm([w.staged_by_desc("FEIRA", b).id])
    assert w.entry(b).status == "confirmed"  # overlap lines do not keep the file pending
    assert w.reports().summary("2026-09", None, True)["total"] == "10.00"
    assert w.reports().summary(OCT, None, True)["total"] == "20.00"


def test_r3_12_overlapping_statement_while_first_is_still_in_review(w: World) -> None:
    a, b_rel = overlapping(w)
    w.drop(b_rel, statement(B_ROWS, period=("15/09/2026", "15/10/2026")))
    assert len(w.staged(a)) == 1
    w.confirm(a)
    assert w.reports().summary("2026-09", None, True)["total"] == "10.00"


def test_r5_2_edit_staged_reject_and_accept_suggestion(w: World) -> None:
    rel = inter(w, [Line(20, 9, 2026, "LOJA NOVA (Parcela 1 de 3)", "30.00")])
    line = w.staged(rel)[0]
    res = edit_staged(w.repo, line.id, {"reject": "create_plan"}, w.clock.now())
    assert res["transaction"]["review"]["suggestions"][0]["rejected"] is True
    assert w.repo.get("annotations", line.fingerprint).link_choices == {"create_plan": "rejected"}
    res = edit_staged(w.repo, line.id, {"accept": "create_plan"}, w.clock.now())
    assert res["transaction"]["review"]["suggestions"][0]["rejected"] is False
    assert w.repo.get("annotations", line.fingerprint).link_choices == {}
    edit_staged(w.repo, line.id, {"reject": "create_plan"}, w.clock.now())
    w.confirm(rel)
    assert w.repo.all("installment_plans") == []  # rejected → no plan


def test_r3_12_same_pdf_in_two_paths_is_duplicate(w: World) -> None:
    data = inter_invoice([Line(20, 9, 2026, "MERCADO BOM", "100.00")])
    w.drop("faturas/a.pdf", data)
    w.drop("faturas/copia/a.pdf", data)
    assert w.entry("faturas/copia/a.pdf").status == "duplicate"
    assert len(w.staged()) == 1


def test_reconcile_manual_ignores_non_provisional(w: World) -> None:
    from expense_tracker.domain.models import Source, Transaction

    tx = Transaction(
        id="t",
        source=Source(type="manual"),
        card_id="card_inter",
        purchase_date=date(2026, 9, 1),
        invoice_month=OCT,
        description="X",
        amount=D("1.00"),
    )
    assert reconcile_manual(w.repo, tx, w.clock.now()) == {"status": "none"}


def test_r10_3_retroactive_manual_split_reaches_confirmed_line_and_balances(w: World) -> None:
    # final review P1-1: the manual's 50/50 split must win and change "a receber"
    rel = inter(w, [Line(20, 9, 2026, "RESTAURANTE BOM", "120.00")])
    w.confirm(rel)
    half = [{"user_id": ME, "pct": "50"}, {"user_id": ANA, "pct": "50"}]
    res = w.manual(purchase_date=date(2026, 9, 20), amount="120.00",
                   description="Restaurante Bom", category_id=HOME, card_id="card_inter",
                   allocations=half)  # fmt: skip
    assert res["reconciliation"]["status"] == "absorbed"
    tx = tx_by_desc(w, "RESTAURANTE")
    assert tx.allocation_origin == "manual"
    assert tx.allocations == [Share(user_id=ME, pct=D("50")), Share(user_id=ANA, pct=D("50"))]


def test_r8_6_matched_manual_note_reaches_confirmed_line(w: World) -> None:
    # refuter P2: the note of the absorbed manual is on the confirmed transaction
    w.manual(purchase_date=date(2026, 9, 20), amount="80.00", description="Farmacia",
             category_id=HOME, card_id="card_inter", note="remédio da mãe")  # fmt: skip
    rel = inter(w, [Line(20, 9, 2026, "FARMACIA", "80.00")])
    w.confirm(rel)
    assert tx_by_desc(w, "FARMACIA").note == "remédio da mãe"
