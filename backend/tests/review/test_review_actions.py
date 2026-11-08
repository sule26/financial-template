"""Review actions: edit_staged (docs/09 "Revisão"), rule suggestion (R5.4), manual check (R10.3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest

from conftest import ANA, FOOD, HOME, World
from expense_tracker.domain.models import Annotation, Kind, Share, Source, Transaction
from expense_tracker.review.actions import edit_staged, reconcile_manual, rule_suggestion
from expense_tracker.review.confirm import ReviewError
from fixtures.files import Line, inter_invoice


@pytest.fixture
def w(world: World) -> World:
    return world.base()


def one_line(
    w: World, desc: str = "PADARIA SOL", rel: str = "faturas/a.pdf", due: str = "15/10/2026"
) -> Transaction:
    w.drop(rel, inter_invoice([Line(20, 9, 2026, desc, "10.00")], due=due))
    return w.staged(rel)[0]


def test_r5_2_edit_unknown_line(w: World) -> None:
    with pytest.raises(ReviewError) as err:
        edit_staged(w.repo, "tx_nope", {"category_id": FOOD}, w.clock.now())
    assert err.value.code == "not_found"


def test_r5_2_edit_with_unknown_category_is_rejected(w: World) -> None:
    line = one_line(w)
    with pytest.raises(ReviewError) as err:
        edit_staged(w.repo, line.id, {"category_id": "cat_ghost"}, w.clock.now())
    assert err.value.code == "reference_not_found"


def test_r5_2_every_edit_is_an_annotation_by_fingerprint(w: World) -> None:
    line = one_line(w)
    alloc = [Share(user_id=ANA, pct=D("100"))]
    res = edit_staged(
        w.repo,
        line.id,
        {"category_id": HOME, "allocations": alloc, "kind": "fee", "note": "taxa"},
        w.clock.now(),
    )
    tx = res["transaction"]
    assert (tx["category_id"], tx["kind"], tx["note"], tx["allocation_origin"]) == (
        HOME,
        "fee",
        "taxa",
        "manual",
    )
    ann = w.repo.get("annotations", line.fingerprint)
    assert (ann.category_id, ann.kind, ann.note, ann.allocations) == (HOME, Kind.FEE, "taxa", alloc)
    assert (ann.description, ann.amount, ann.owner_id) == ("PADARIA SOL", D("10.00"), "card_inter")
    # clearing the division keeps the previous origin; clearing the category flags it again
    res = edit_staged(w.repo, line.id, {"allocations": None, "category_id": None}, w.clock.now())
    assert res["transaction"]["allocation_origin"] == "manual"
    assert res["transaction"]["review"]["warnings"] == ["category_missing"]


def test_r14_8_card_invoice_line_only_takes_spending_or_investment_kinds(w: World) -> None:
    line = one_line(w)
    for kind in ("transfer", "income", "settlement"):
        with pytest.raises(ReviewError, match="card invoice line") as exc:
            edit_staged(w.repo, line.id, {"kind": kind}, w.clock.now())
        assert exc.value.code == "invalid_kind"
    for kind in ("refund", "fee", "investment", "expense"):
        res = edit_staged(w.repo, line.id, {"kind": kind}, w.clock.now())
        assert res["transaction"]["kind"] == kind


def test_r5_2_choose_unknown_suggestion_type(w: World) -> None:
    line = one_line(w)
    with pytest.raises(ReviewError, match="no suggestion"):
        edit_staged(
            w.repo, line.id, {"choose": {"type": "choose_plan", "target_id": "x"}}, w.clock.now()
        )


# ------------------------------------------------------------------ rule suggestion (R5.4)


def test_r5_4_no_suggestion_without_annotation_content(w: World) -> None:
    line = one_line(w)
    assert rule_suggestion(w.repo, line) is None  # no annotation yet
    edit_staged(w.repo, line.id, {"note": "x"}, w.clock.now())
    assert rule_suggestion(w.repo, w.repo.get("staging", line.id)) is None  # note only
    assert rule_suggestion(w.repo, line.model_copy(update={"fingerprint": None})) is None


def test_r5_4_uses_annotation_of_a_removed_file(w: World) -> None:
    # the other edit's line is gone (file removed): its annotation still remembers the file
    w.repo.put(
        "annotations",
        Annotation(
            fingerprint="fp_gone",
            category_id=HOME,
            description="Padaria Sol",
            source_files=["sha_old"],
        ),
    )
    line = one_line(w)
    res = edit_staged(w.repo, line.id, {"category_id": HOME}, w.clock.now())
    assert res["rule_suggestion"]["category_id"] == HOME
    assert res["rule_suggestion"]["priority"] == 10  # no rules yet: 0 + 10


def test_r5_4_different_edit_or_description_gives_no_suggestion(w: World) -> None:
    w.repo.put(
        "annotations",
        Annotation(
            fingerprint="fp_1",
            category_id=FOOD,
            description="Padaria Sol",
            source_files=["sha_old"],
        ),
    )
    w.repo.put(
        "annotations",
        Annotation(
            fingerprint="fp_2",
            category_id=HOME,
            description="Outra Coisa",
            source_files=["sha_old"],
        ),
    )
    w.repo.put(
        "annotations", Annotation(fingerprint="fp_3", category_id=HOME, description="Padaria Sol")
    )
    line = one_line(w)
    res = edit_staged(w.repo, line.id, {"category_id": HOME}, w.clock.now())
    assert res["rule_suggestion"] is None


# ------------------------------------------------------------------ reconcile_manual (R10.3)


def manual_tx(**kw: object) -> Transaction:
    data: dict[str, object] = {
        "id": "man",
        "source": Source(type="manual"),
        "provisional": True,
        "card_id": "card_inter",
        "purchase_date": date(2026, 9, 20),
        "invoice_month": "2026-10",
        "description": "Padaria Sol",
        "amount": D("10.00"),
        "category_id": FOOD,
    }
    data.update(kw)
    return Transaction(**data)  # type: ignore[arg-type]


def test_r10_3_manual_without_document_stays_projected(w: World) -> None:
    assert reconcile_manual(w.repo, manual_tx(), w.clock.now()) == {"status": "projected"}
    acc = manual_tx(card_id=None, account_id="acc_me", payment_method="pix")
    assert reconcile_manual(w.repo, acc, w.clock.now()) == {"status": "projected"}


def test_r10_3_manual_on_additional_card_checks_main_card_invoice(w: World) -> None:
    w.catalog.create(
        "cards",
        {
            "id": "card_add",
            "name": "Adicional",
            "parent_card_id": "card_inter",
            "owners": [{"user_id": ANA, "pct": "100"}],
            "responsible_user_id": ANA,
            "last_digits": ["9999"],
        },
    )
    one_line(w)
    m = manual_tx(card_id="card_add")
    w.repo.put("transactions", m)
    res = reconcile_manual(w.repo, m, w.clock.now())
    assert res["status"] == "absorbed"
    assert w.repo.get("transactions", "man") is None


def test_r10_3_absorbed_into_confirmed_line_fills_missing_category(w: World) -> None:
    line = one_line(w)
    # a transfer line is confirmable without category (data staged before R14.8)
    w.repo.put("staging", line.model_copy(update={"kind": Kind.TRANSFER}))
    w.confirm("faturas/a.pdf")
    m = manual_tx(note="pão")
    w.repo.put("transactions", m)
    res = reconcile_manual(w.repo, m, w.clock.now())
    assert res["status"] == "absorbed"
    tx = w.repo.get("transactions", line.id)
    assert tx.category_id == FOOD
    ann = w.repo.get("annotations", line.fingerprint)
    assert (ann.category_id, ann.note) == (FOOD, "pão")
