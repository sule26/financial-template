"""Confirmation effects (docs/09 "Ao confirmar") and removal cascade (docs/05 "Cascata", R3.13)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from typing import Any

import pytest

from conftest import ANA, FOOD, HOME, ME, World
from expense_tracker.domain.documents import ManifestEntry
from expense_tracker.domain.models import (
    Annotation,
    InstallmentRef,
    Kind,
    Links,
    PaymentMethod,
    ReviewInfo,
    Share,
    Source,
    Suggestion,
    Transaction,
)
from expense_tracker.review.confirm import (
    Confirmer,
    ReviewError,
    active_suggestion,
    move_lines,
    refresh_status,
    remove_lines,
)
from expense_tracker.review.fingerprint import derived_id
from fixtures.files import Line, inter_invoice, statement

OCT = "2026-10"


@pytest.fixture
def w(world: World) -> World:
    world.base()
    world.categorize_all(FOOD)
    return world


def staged(w: World, tid: str, *suggestions: Suggestion, **kw: Any) -> Transaction:
    """Put a hand-made line in staging (unit-level checks of a single action)."""
    data: dict[str, Any] = {
        "id": tid,
        "fingerprint": f"fp_{tid}",
        "source": Source(type="import", sha256="sha_unit", path="faturas/u.pdf", line=0),
        "card_id": "card_inter",
        "purchase_date": date(2026, 9, 20),
        "invoice_month": OCT,
        "description": "LINHA",
        "amount": D("10.00"),
        "category_id": FOOD,
        "review": ReviewInfo(suggestions=list(suggestions)),
    }
    data.update(kw)
    tx = Transaction(**data)
    w.repo.put("staging", tx)
    return tx


def confirm(w: World, *ids: str) -> dict[str, Any]:
    return Confirmer(w.repo, w.clock.now()).confirm(ids)


def got(w: World, tid: str) -> Transaction:
    tx = w.repo.get("transactions", tid)
    assert tx is not None
    return tx


# ------------------------------------------------------------------ guards


def test_confirm_unknown_line_is_not_found(w: World) -> None:
    with pytest.raises(ReviewError) as err:
        confirm(w, "tx_nope")
    assert err.value.code == "not_found"


def test_confirm_blocks_open_choose_suggestion_even_if_status_pending(w: World) -> None:
    staged(w, "a", Suggestion(type="choose_investment", candidates=["x", "y"]))
    with pytest.raises(ReviewError, match="needs_choice"):
        confirm(w, "a")


def test_r1_11_settlement_like_kinds_do_not_need_category(w: World) -> None:
    staged(w, "a", kind=Kind.TRANSFER, category_id=None)
    confirm(w, "a")
    assert got(w, "a").review is None  # review data is dropped on confirmation


def test_active_suggestion_skips_rejected_and_targetless() -> None:
    tx = Transaction(
        id="t",
        source=Source(type="import"),
        card_id="c",
        purchase_date=date(2026, 9, 1),
        invoice_month=OCT,
        description="x",
        amount=D("1.00"),
        review=ReviewInfo(
            suggestions=[
                Suggestion(type="link_plan", target_id="p", rejected=True),
                Suggestion(type="choose_plan", candidates=["p"]),
                Suggestion(type="link_anticipation_discount", data={"plan_fingerprint": "fp"}),
            ]
        ),
    )
    s = active_suggestion(tx)
    assert s is not None and s.type == "link_anticipation_discount"
    assert active_suggestion(tx.model_copy(update={"review": None})) is None


# ------------------------------------------------------------------ actions with missing targets


@pytest.mark.parametrize(
    "stype",
    [
        "match_manual",
        "link_investment",
        "apply_annotation",
        "link_anticipation",
        "internal_transfer",
    ],
)
def test_actions_with_vanished_target_confirm_plainly(w: World, stype: str) -> None:
    staged(w, "a", Suggestion(type=stype, target_id="gone"), kind=Kind.EXPENSE)
    confirm(w, "a")
    tx = got(w, "a")
    assert tx.amount == D("10.00")
    assert tx.links.investment_id is None and tx.links.anticipation_plan_id is None


def test_unknown_suggestion_type_is_ignored(w: World) -> None:
    staged(w, "a", Suggestion(type="something_new", target_id="x"))
    confirm(w, "a")
    assert got(w, "a").links == Links()


# ------------------------------------------------------------------ plans


def test_create_plan_reuses_plan_kept_as_manual(w: World) -> None:
    # a plan kept as manual after its origin vanished is linked again when the line returns
    tx = staged(
        w,
        "a",
        Suggestion(type="create_plan", data={"n": 1, "of": 3}),
        installment=InstallmentRef(n=1, of=3),
        amount=D("30.00"),
    )
    pid = derived_id("plan", tx.fingerprint)  # type: ignore[arg-type]
    w.catalog.create(
        "installment_plans",
        {
            "id": pid,
            "origin": {"type": "manual", "fingerprint": tx.fingerprint},
            "card_id": "card_inter",
            "description": "Edited",
            "total_installments": 3,
            "first_invoice_month": OCT,
            "total_amount": "90.00",
            "allocations": [{"user_id": ANA, "pct": "100"}],
        },
    )
    confirm(w, "a")
    plan = w.repo.get("installment_plans", pid)
    assert plan.origin.type == "import"
    assert plan.description == "Edited"  # my edits on the plan are kept
    assert got(w, "a").installment.plan_id == pid


def test_create_plan_keeps_manual_division_of_the_line(w: World) -> None:
    alloc = [Share(user_id=ANA, pct=D("100"))]
    tx = staged(
        w,
        "a",
        Suggestion(type="create_plan"),
        installment=InstallmentRef(n=2, of=4),
        amount=D("25.00"),
        allocations=alloc,
        allocation_origin="manual",
        description="loja   nova",
    )
    confirm(w, "a")
    plan = w.repo.get("installment_plans", derived_id("plan", tx.fingerprint))  # type: ignore[arg-type]
    assert plan.allocations == alloc
    assert (plan.first_invoice_month, plan.total_amount) == ("2026-09", D("100.00"))
    assert plan.description == "Loja Nova"


def test_refund_plan_without_installment_uses_plan_size(w: World) -> None:
    w.catalog.create(
        "installment_plans",
        {
            "id": "plan_r",
            "card_id": "card_inter",
            "description": "LOJA",
            "total_installments": 4,
            "first_invoice_month": OCT,
            "total_amount": "100.00",
        },
    )
    staged(
        w,
        "a",
        Suggestion(type="refund_plan", target_id="plan_r"),
        amount=D("-10.00"),
        kind=Kind.REFUND,
    )
    staged(
        w,
        "b",
        Suggestion(type="refund_plan", target_id="ghost"),
        amount=D("-10.00"),
        kind=Kind.REFUND,
        installment=InstallmentRef(n=2, of=5),
    )
    confirm(w, "a", "b")
    assert got(w, "a").installment == InstallmentRef(plan_id="plan_r", n=1, of=4)
    assert got(w, "b").installment == InstallmentRef(plan_id="ghost", n=2, of=5)


def test_choose_plan_links_the_chosen_plan(w: World) -> None:
    staged(
        w,
        "a",
        Suggestion(type="choose_plan", target_id="plan_c", candidates=["plan_c"]),
        installment=InstallmentRef(n=3, of=10),
    )
    confirm(w, "a")
    assert got(w, "a").installment.plan_id == "plan_c"


def test_bank_anticipation_without_existing_anticipation_uses_from_n(w: World) -> None:
    w.catalog.create(
        "installment_plans",
        {
            "id": "plan_b",
            "card_id": "card_inter",
            "description": "LOJA",
            "total_installments": 5,
            "first_invoice_month": "2026-08",
            "total_amount": "100.00",
        },
    )
    staged(
        w,
        "a",
        Suggestion(type="bank_anticipation", target_id="plan_b", data={"from_n": 4}),
        installment=InstallmentRef(n=4, of=5),
        amount=D("20.00"),
    )
    staged(
        w,
        "b",
        Suggestion(type="bank_anticipation", target_id="plan_b", data={"from_n": 4}),
        installment=InstallmentRef(n=5, of=5),
        amount=D("20.00"),
    )
    confirm(w, "a", "b")
    ant = w.repo.get("installment_plans", "plan_b").anticipation
    assert (ant.from_n, ant.target_month, ant.amount) == (4, OCT, D("40.00"))
    assert ant.linked_fingerprints == ["fp_a", "fp_b"]


def test_anticipation_tag_line_without_installment_uses_last_n(w: World) -> None:
    w.catalog.create(
        "installment_plans",
        {
            "id": "plan_t",
            "card_id": "card_inter",
            "description": "LOJA",
            "total_installments": 6,
            "first_invoice_month": "2026-08",
            "total_amount": "60.00",
        },
    )
    staged(w, "a", Suggestion(type="link_anticipation", target_id="plan_t"), amount=D("10.00"))
    confirm(w, "a")
    plan = w.repo.get("installment_plans", "plan_t")
    assert plan.anticipation.from_n == 6
    assert got(w, "a").installment is None
    assert got(w, "a").links.anticipation_plan_id == "plan_t"


def test_r7_5_discount_alone_leaves_amount_unset(w: World) -> None:
    w.catalog.create(
        "installment_plans",
        {
            "id": "plan_d",
            "card_id": "card_inter",
            "description": "LOJA",
            "total_installments": 6,
            "first_invoice_month": "2026-08",
            "total_amount": "60.00",
            "anticipation": {"from_n": 5, "target_month": OCT},
        },
    )
    staged(
        w,
        "a",
        Suggestion(type="link_anticipation_discount", target_id="plan_d"),
        amount=D("-2.00"),
        kind=Kind.REFUND,
    )
    confirm(w, "a")
    ant = w.repo.get("installment_plans", "plan_d").anticipation
    assert ant.linked_fingerprints == ["fp_a"]
    assert ant.amount is None  # a negative sum is not a real anticipation value


# ------------------------------------------------------------------ other links


def test_match_manual_moves_recurring_link_and_keeps_existing_annotation(w: World) -> None:
    w.catalog.create(
        "recurring_purchases",
        {
            "id": "rec_r",
            "description": "RACAO",
            "estimated_amount": "100.00",
            "every": {"value": 30},
            "last_date": "2026-09-01",
            "card_id": "card_inter",
        },
    )
    manual = Transaction(
        id="man",
        source=Source(type="manual"),
        provisional=True,
        card_id="card_inter",
        purchase_date=date(2026, 9, 20),
        invoice_month=OCT,
        description="Racao",
        amount=D("10.00"),
        category_id=HOME,
        note="manual note",
        links=Links(recurring_purchase_id="rec_r"),
    )
    w.repo.put("transactions", manual)
    w.repo.put("annotations", Annotation(fingerprint="fp_a", note="mine", source_files=["s0"]))
    staged(w, "a", Suggestion(type="match_manual", target_id="man"))
    confirm(w, "a")
    assert w.repo.get("transactions", "man") is None
    assert got(w, "a").links.recurring_purchase_id == "rec_r"
    ann = w.repo.get("annotations", "fp_a")
    assert (ann.note, ann.category_id) == ("mine", HOME)  # my annotation wins, gaps from manual
    assert ann.source_files == ["s0", "sha_unit"]  # remembers the file it was confirmed from


def test_link_recurring_does_not_move_anchor_backwards(w: World) -> None:
    w.catalog.create(
        "recurring_purchases",
        {
            "id": "rec_r",
            "description": "RACAO",
            "estimated_amount": "100.00",
            "every": {"value": 30},
            "last_date": "2026-09-25",
            "card_id": "card_inter",
        },
    )
    staged(w, "a", Suggestion(type="link_recurring", target_id="rec_r"))
    confirm(w, "a")
    assert w.repo.get("recurring_purchases", "rec_r").last_date == date(2026, 9, 25)
    assert got(w, "a").links.recurring_purchase_id == "rec_r"


def test_r9_4_investment_on_card_is_kind_investment_and_idempotent(w: World) -> None:
    w.catalog.create(
        "investments",
        {
            "id": "inv_p",
            "name": "Previdência",
            "type": "pension",
            "owners": [{"user_id": ME, "pct": "100"}],
            "movements": [
                {
                    "date": "2026-08-01",
                    "type": "contribution",
                    "amount": "1.00",
                    "origin": {"type": "import", "fingerprint": "fp_a"},
                }
            ],
        },
    )
    staged(
        w,
        "a",
        Suggestion(type="choose_investment", target_id="inv_p", data={"movement": "contribution"}),
        amount=D("300.00"),
    )
    confirm(w, "a")
    assert got(w, "a").kind is Kind.INVESTMENT
    movements = w.repo.get("investments", "inv_p").movements
    assert [(m.date, m.amount) for m in movements] == [(date(2026, 9, 20), D("300.00"))]


def test_settlement_keeps_previous_note(w: World) -> None:
    from expense_tracker.domain.models import Settlement

    sid = derived_id("set", "fp_a")
    w.repo.put(
        "settlements",
        Settlement(
            id=sid,
            from_user_id="u_pai",
            to_user_id=ME,
            amount=D("1.00"),
            date=date(2026, 9, 1),
            month=OCT,
            note="mesada",
        ),
    )
    staged(
        w,
        "a",
        Suggestion(type="settlement", target_id="u_pai", data={"to_user_id": ME}),
        card_id=None,
        account_id="acc_me",
        payment_method=PaymentMethod.TRANSFER,
        kind=Kind.INCOME,
        amount=D("200.00"),
    )
    confirm(w, "a")
    st = w.repo.get("settlements", sid)
    assert (st.note, st.amount, st.origin.type) == ("mesada", D("200.00"), "import")


def test_apply_annotation_copies_edits(w: World) -> None:
    alloc = [Share(user_id=ANA, pct=D("100"))]
    w.repo.put(
        "annotations",
        Annotation(fingerprint="fp_old", category_id=HOME, allocations=alloc, note="n"),
    )
    staged(w, "a", Suggestion(type="apply_annotation", target_id="fp_old"))
    confirm(w, "a")
    tx = got(w, "a")
    assert (tx.category_id, tx.allocations, tx.allocation_origin, tx.note) == (
        HOME,
        alloc,
        "manual",
        "n",
    )
    assert w.repo.get("annotations", "fp_a").category_id == HOME


# ------------------------------------------------------------------ manifest status


def manifest(w: World, sha: str = "sha_unit", **kw: Any) -> ManifestEntry:
    e = ManifestEntry(
        path="faturas/u.pdf",
        sha256=sha,
        size=1,
        mtime=w.clock.now(),
        kind="fatura",
        card_id="card_inter",
        invoice_month=OCT,
        **kw,
    )
    w.repo.put("import_manifest", e)
    return e


def test_refresh_status_follows_confirmation(w: World) -> None:
    manifest(w)
    staged(w, "a")
    staged(w, "b")
    refresh_status(w.repo, "sha_unit")
    assert w.entry("faturas/u.pdf").status == "pending_review"
    confirm(w, "a")
    assert w.entry("faturas/u.pdf").status == "partially_confirmed"
    confirm(w, "b")
    assert w.entry("faturas/u.pdf").status == "confirmed"
    refresh_status(w.repo, "sha_unknown")  # no entry: nothing happens


def test_refresh_status_candidate_replacement_stays_pending(w: World) -> None:
    manifest(w, supersedes_candidate="faturas/old.pdf")
    refresh_status(w.repo, "sha_unit")
    assert w.entry("faturas/u.pdf").status == "pending_review"


def test_move_lines_reassigns_kept_lines(w: World) -> None:
    staged(w, "a")
    staged(w, "b")
    new = manifest(w, sha="sha_new")
    move_lines(w.repo, "sha_unit", new, {"fp_a"})
    assert w.repo.get("staging", "a").source.sha256 == "sha_new"
    assert w.repo.get("staging", "b").source.sha256 == "sha_unit"


# ------------------------------------------------------------------ cascade (R3.13)


def test_remove_lines_nothing_to_do(w: World) -> None:
    assert remove_lines(w.repo, set(), w.clock.now()) == []
    staged(w, "a")
    staged(w, "a2", fingerprint="fp_a", source=Source(type="import", sha256="other"))
    # the fingerprint still exists in another document: derived objects are untouched
    assert remove_lines(w.repo, {"fp_a"}, w.clock.now(), sha="sha_unit") == []
    assert w.repo.get("staging", "a2") is not None


def test_r3_13_removing_7b_invoice_removes_plan_and_putting_back_recreates_it(w: World) -> None:
    lines = [
        Line(1, 2, 2026, "LOJA Z (Parcela 9 de 10)", "30.00"),
        Line(1, 2, 2026, "LOJA Z (Parcela 10 de 10)", "30.00"),
    ]
    data = inter_invoice(lines, due="15/10/2026")
    w.drop("faturas/z.pdf", data)
    w.confirm("faturas/z.pdf")
    [plan] = w.repo.all("installment_plans")
    w.remove("faturas/z.pdf")
    assert w.repo.all("installment_plans") == []
    w.drop("faturas/z.pdf", data)
    w.confirm("faturas/z.pdf")
    [again] = w.repo.all("installment_plans")
    assert again.id == plan.id
    assert again.anticipation.amount == D("30.00")


def test_r3_13_removing_lines_linked_to_existing_anticipation(w: World) -> None:
    w.catalog.create(
        "installment_plans",
        {
            "id": "plan_y",
            "card_id": "card_inter",
            "description": "LOJA Y",
            "total_installments": 10,
            "first_invoice_month": "2026-02",
            "total_amount": "300.00",
            "anticipation": {"from_n": 9, "target_month": OCT},
        },
    )
    rel = w.drop(
        "faturas/y.pdf",
        inter_invoice(
            [
                Line(1, 2, 2026, "LOJA Y (Parcela 9 de 10)", "30.00"),
                Line(1, 2, 2026, "LOJA Y (Parcela 10 de 10)", "30.00"),
            ]
        ),
    )
    w.confirm(rel)
    assert w.repo.get("installment_plans", "plan_y").anticipation.amount == D("60.00")
    w.remove(rel)
    ant = w.repo.get("installment_plans", "plan_y").anticipation
    assert (ant.linked_fingerprints, ant.amount) == ([], None)  # back to a forecast
    assert w.projection()[OCT] == D("60.00")


def test_r3_13_plan_still_referenced_by_another_invoice_is_kept(w: World) -> None:
    sep = w.drop(
        "faturas/set.pdf",
        inter_invoice([Line(1, 8, 2026, "LOJA N (Parcela 1 de 5)", "20.00")], due="15/09/2026"),
    )
    w.confirm(sep)
    [plan] = w.repo.all("installment_plans")
    octo = w.drop(
        "faturas/out.pdf", inter_invoice([Line(1, 8, 2026, "LOJA N (Parcela 2 de 5)", "20.00")])
    )
    w.confirm(octo)
    assert any(t.installment.plan_id == plan.id and t.installment.n == 2 for t in w.confirmed())
    w.remove(sep)
    assert [p.id for p in w.repo.all("installment_plans")] == [plan.id]


def test_r3_13_edited_plan_is_kept_as_manual_when_origin_disappears(w: World) -> None:
    rel = w.drop(
        "faturas/n.pdf", inter_invoice([Line(1, 9, 2026, "LOJA N (Parcela 1 de 5)", "20.00")])
    )
    w.confirm(rel)
    [plan] = w.repo.all("installment_plans")
    w.repo.put(
        "installment_plans",
        plan.model_copy(update={"allocations": [Share(user_id=ANA, pct=D("100"))]}),
    )
    w.remove(rel)
    [kept] = w.repo.all("installment_plans")
    assert kept.origin.type == "manual"
    assert "origem removida" in kept.warnings
    # putting it back links the same plan again, without a duplicate
    rel = w.drop(
        "faturas/n.pdf", inter_invoice([Line(1, 9, 2026, "LOJA N (Parcela 1 de 5)", "20.00")])
    )
    w.confirm(rel)
    [back] = w.repo.all("installment_plans")
    assert back.id == plan.id
    assert back.allocations == [Share(user_id=ANA, pct=D("100"))]
    assert w.confirmed()[0].installment.plan_id == plan.id


def test_r3_13_investment_movement_becomes_manual_and_relinks_on_return(w: World) -> None:
    w.catalog.create(
        "investments",
        {
            "id": "inv_cdb",
            "name": "CDB",
            "owners": [{"user_id": ME, "pct": "100"}],
            "account_id": "acc_me",
        },
    )
    data = statement(
        [("06/10/2026", "APLICACAO CDB", "300.00")], period=("01/10/2026", "31/10/2026")
    )
    w.drop("extratos/c.pdf", data)
    w.confirm("extratos/c.pdf")
    w.remove("extratos/c.pdf")
    [m] = w.repo.get("investments", "inv_cdb").movements
    assert (m.origin.type, m.warnings) == ("manual", ["origem removida"])
    w.drop("extratos/c.pdf", data)
    [m] = w.repo.get("investments", "inv_cdb").movements
    assert (m.origin.type, m.warnings) == ("import", [])


def test_r3_13_settlement_relinks_when_statement_returns(w: World) -> None:
    data = statement(
        [("05/10/2026", "PIX RECEBIDO JOSE DA SILVA", "-200.00")],
        period=("01/10/2026", "31/10/2026"),
    )
    w.drop("extratos/c.pdf", data)
    w.confirm("extratos/c.pdf")
    w.remove("extratos/c.pdf")
    w.drop("extratos/c.pdf", data)
    [st] = w.repo.all("settlements")
    assert (st.origin.type, st.warnings) == ("import", [])


def test_r3_13_internal_transfer_link_is_cleared_when_counterpart_disappears(w: World) -> None:
    w.repo.put(
        "transactions",
        Transaction(
            id="keep",
            fingerprint="fp_keep",
            kind=Kind.TRANSFER,
            source=Source(type="import", sha256="sha_keep"),
            payment_method=PaymentMethod.TRANSFER,
            account_id="acc_me",
            purchase_date=date(2026, 10, 7),
            invoice_month=OCT,
            description="TED",
            amount=D("300.00"),
            links=Links(internal_transfer_fingerprint="fp_gone"),
        ),
    )
    remove_lines(w.repo, {"fp_gone"}, w.clock.now())
    assert got(w, "keep").links.internal_transfer_fingerprint is None


def test_r14_26_match_manual_keeps_the_bill_link_and_month(w: World) -> None:
    # A bill paid by hand (linked to the subscription) and later absorbed by the imported line:
    # the imported line keeps paying the same bill month (review finding P1-2).
    w.catalog.create(
        "subscriptions",
        {
            "id": "sub_luz",
            "description": "LUZ",
            "amount": "100.00",
            "start_month": "2026-01",
            "card_id": "card_inter",
            "group": "household",
        },
    )
    manual = Transaction(
        id="man",
        source=Source(type="manual"),
        provisional=True,
        card_id="card_inter",
        purchase_date=date(2026, 9, 20),
        invoice_month=OCT,
        description="Luz",
        amount=D("10.00"),
        category_id=HOME,
        links=Links(subscription_id="sub_luz", subscription_month="2026-09"),
    )
    w.repo.put("transactions", manual)
    staged(w, "a", Suggestion(type="match_manual", target_id="man"))
    confirm(w, "a")
    links = got(w, "a").links
    assert (links.subscription_id, links.subscription_month) == ("sub_luz", "2026-09")
