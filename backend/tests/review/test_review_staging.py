"""Staging: owner identification (docs/06), defaults by precedence (docs/08), annotations,
link choices and orphan annotations (docs/09)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from conftest import ANA, FOOD, HOME, ME, TECH, World
from expense_tracker.domain.documents import CardChoice, ManifestEntry
from expense_tracker.domain.models import (
    Annotation,
    Kind,
    PaymentMethod,
    ReviewInfo,
    Share,
    Suggestion,
)
from expense_tracker.domain.parse_result import ParseResult, RawLine
from expense_tracker.review.staging import (
    Identified,
    OwnerUnresolved,
    apply_defaults,
    build_lines,
    identify,
    last_category_lookup,
    orphan_suggestion,
    stage_document,
)

NOW = datetime(2026, 10, 12, 10, 0)


def entry(path: str = "faturas/x.pdf", kind: str = "fatura", sha: str = "sha_x") -> ManifestEntry:
    return ManifestEntry(path=path, sha256=sha, size=1, mtime=NOW, kind=kind)  # type: ignore[arg-type]


def raw(desc: str, amount: str, i: int = 0, **kw: Any) -> RawLine:
    kw.setdefault("date", date(2026, 9, 10))
    return RawLine(index=i, description=desc, amount=Decimal(amount), **kw)


def invoice(*lines: RawLine, **kw: Any) -> ParseResult:
    kw.setdefault("invoice_month", "2026-10")
    kw.setdefault("profile_id", "inter-fatura")
    return ParseResult(kind="fatura", lines=list(lines), **kw)


def statement_result(*lines: RawLine, **kw: Any) -> ParseResult:
    kw.setdefault("profile_id", "banco-teste-extrato")
    return ParseResult(kind="extrato", lines=list(lines), **kw)


@pytest.fixture
def w(world: World) -> World:
    return world.base()


# ------------------------------------------------------------------ identify (docs/06)


def test_r4_8_statement_account_by_hint_ignoring_spaces(w: World) -> None:
    ident = identify(w.repo, entry(kind="extrato"), statement_result(account_hint="12345 - 6"))
    # "12345 - 6" without spaces is "12345-6"
    assert ident.account_id == "acc_me"


def test_r4_8_statement_single_account_of_the_profile(w: World) -> None:
    ident = identify(w.repo, entry(kind="extrato"), statement_result(account_hint=None))
    assert ident.account_id == "acc_me"


def test_r4_8_statement_choice_by_sha_and_unresolved(w: World) -> None:
    res = statement_result(profile_id="other-bank", account_hint="000")
    with pytest.raises(OwnerUnresolved):
        identify(w.repo, entry(kind="extrato"), res)
    w.repo.put("card_choices", CardChoice(id="ch1", sha256="sha_x", account_id="acc_me"))
    assert identify(w.repo, entry(kind="extrato"), res).account_id == "acc_me"


def test_r4_8_invoice_card_by_header_digits(w: World) -> None:
    ident = identify(w.repo, entry(), invoice(raw("A", "1"), card_hint="5678"))
    assert ident.card_id == "card_inter"
    assert ident.invoice_month == "2026-10"
    assert ident.line_cards == ["card_inter"]


def test_r4_8_invoice_single_main_card_of_the_profile(w: World) -> None:
    ident = identify(w.repo, entry(), invoice(raw("A", "1")))
    assert ident.card_id == "card_inter"


def test_r4_8_invoice_card_by_line_hint_and_unresolved(w: World) -> None:
    res = invoice(raw("A", "1", card_hint="1234"), profile_id="unknown")
    assert identify(w.repo, entry(), res).card_id == "card_inter"
    with pytest.raises(OwnerUnresolved, match="cartão"):
        identify(w.repo, entry(), invoice(raw("A", "1"), profile_id="unknown"))


def test_r4_8_invoice_choice_gives_card_and_month(w: World) -> None:
    res = invoice(raw("A", "1"), profile_id="unknown", invoice_month=None, card_hint="0000")
    with pytest.raises(OwnerUnresolved):
        identify(w.repo, entry(), res)
    # a choice remembered by (profile, hint) applies to later files of the same card
    w.repo.put(
        "card_choices",
        CardChoice(
            id="c",
            profile_id="unknown",
            card_hint="0000",
            card_id="card_inter",
            invoice_month="2026-09",
        ),
    )
    ident = identify(w.repo, entry(sha="other"), res)
    assert (ident.card_id, ident.invoice_month) == ("card_inter", "2026-09")


def test_r4_8_invoice_without_month_is_unresolved(w: World) -> None:
    with pytest.raises(OwnerUnresolved, match="mês"):
        identify(w.repo, entry(), invoice(raw("A", "1"), invoice_month=None))


def test_r6_9_line_cards_of_additional_unknown_and_foreign_cards(w: World) -> None:
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
    w.nubank()
    res = invoice(
        raw("A", "1", 0, card_hint="9999"),
        raw("B", "1", 1, card_hint="4444"),
        raw("C", "1", 2, card_hint="1111"),  # a card of another main card
        raw("D", "1", 3, card_hint="4444"),
        card_hint="1234",
    )
    ident = identify(w.repo, entry(), res)
    assert ident.line_cards == ["card_add", "card_inter", "card_inter", "card_inter"]
    assert ident.warnings == ["unknown_card_hint:4444"]


# ------------------------------------------------------------------ build_lines


def test_build_lines_amounts_kinds_and_methods(w: World) -> None:
    w.catalog.create(
        "accounts",
        {
            "id": "acc_vr",
            "name": "VR",
            "type": "benefit",
            "owners": [{"user_id": ME, "pct": "100"}],
            "responsible_user_id": ME,
        },
    )
    res = statement_result(
        raw("SALDO VR", "-500.00", 0, kind="income"),
        raw("RESTAURANTE", "30.00", 1),
        raw("ESTORNO", "12.00", 2, kind="refund"),
        raw("TED", "-50.00", 3, kind="transfer"),
        raw("PIX X", "20.00", 4, payment_method="pix"),
    )
    lines = build_lines(w.repo, entry(kind="extrato"), res, Identified(account_id="acc_vr"), NOW)
    assert [t.amount for t in lines] == [
        Decimal("500.00"),
        Decimal("30.00"),
        Decimal("-12.00"),
        Decimal("-50.00"),  # transfers keep the sign
        Decimal("20.00"),
    ]
    assert lines[0].income_type == "benefit"
    assert lines[1].payment_method is PaymentMethod.BENEFIT
    assert lines[4].payment_method is PaymentMethod.PIX
    assert all(t.invoice_month == "2026-09" for t in lines)  # statements: month of the date
    assert all(t.card_id is None and t.account_id == "acc_vr" for t in lines)
    assert len({t.fingerprint for t in lines}) == 5
    assert all(t.id == f"tx_{t.id[3:]}" for t in lines)


def test_build_lines_cash_and_checking_methods(w: World) -> None:
    w.catalog.create(
        "accounts",
        {
            "id": "acc_cash",
            "name": "Carteira",
            "type": "cash",
            "owners": [{"user_id": ME, "pct": "100"}],
            "responsible_user_id": ME,
        },
    )
    res = statement_result(raw("FEIRA", "10.00"), raw("SALARIO", "-10.00", 1, kind="income"))
    cash = build_lines(w.repo, entry(kind="extrato"), res, Identified(account_id="acc_cash"), NOW)
    assert cash[0].payment_method is PaymentMethod.CASH
    chk = build_lines(w.repo, entry(kind="extrato"), res, Identified(account_id="acc_me"), NOW)
    assert chk[0].payment_method is PaymentMethod.DEBIT
    assert chk[1].payment_method is PaymentMethod.TRANSFER
    assert chk[1].income_type == "cash"


def test_build_lines_invalid_installment_is_dropped(w: World) -> None:
    res = invoice(raw("X", "10.00", installment_n=11, installment_of=10))
    ident = Identified(card_id="card_inter", line_cards=["card_inter"], invoice_month="2026-10")
    [tx] = build_lines(w.repo, entry(), res, ident, NOW)
    assert tx.installment is None
    assert tx.payment_method is PaymentMethod.CREDIT
    assert tx.invoice_month == "2026-10"


# ------------------------------------------------------------------ precedence (docs/08, R5.3)


def staged_tx(w: World, desc: str = "LOJA X (Parcela 3 de 10)", amount: str = "50.00", **kw: Any):  # type: ignore[no-untyped-def]
    ident = Identified(card_id="card_inter", line_cards=["card_inter"], invoice_month="2026-10")
    [tx] = build_lines(w.repo, entry(), invoice(raw(desc, amount, **kw)), ident, NOW)
    return tx


HALF = [{"user_id": ME, "pct": "50"}, {"user_id": ANA, "pct": "50"}]


def test_r5_3_level_5_and_4_owners_without_anything_else(w: World) -> None:
    tx = apply_defaults(w.repo, staged_tx(w), last_category_lookup(w.repo))
    assert tx.allocation_origin == "owners:card"
    assert tx.category_id is None


def test_r5_3_rule_then_plan_then_annotation(w: World) -> None:
    w.catalog.create(
        "rules",
        {
            "id": "rule_loja",
            "priority": 10,
            "when": {"description_regex": "LOJA"},
            "then": {"category_id": HOME, "allocations": [{"user_id": ANA, "pct": "100"}]},
        },
    )
    w.catalog.create(
        "installment_plans",
        {
            "id": "plan_x",
            "card_id": "card_inter",
            "description": "LOJA X",
            "total_installments": 10,
            "first_invoice_month": "2026-08",
            "total_amount": "500.00",
            "category_id": TECH,
            "allocations": HALF,
        },
    )
    lookup = last_category_lookup(w.repo)
    base = staged_tx(w)
    by_rule = apply_defaults(w.repo, base, lookup)
    assert (by_rule.category_id, by_rule.allocation_origin) == (HOME, "rule:rule_loja")

    linked = base.model_copy(
        update={
            "review": ReviewInfo(suggestions=[Suggestion(type="link_plan", target_id="plan_x")])
        }
    )
    by_plan = apply_defaults(w.repo, linked, lookup)
    assert (by_plan.category_id, by_plan.allocation_origin) == (TECH, "plan:plan_x")
    assert by_plan.allocations == [
        Share(user_id=ME, pct=Decimal("50")),
        Share(user_id=ANA, pct=Decimal("50")),
    ]

    # a rejected suggestion does not count as a link
    rejected = base.model_copy(
        update={
            "review": ReviewInfo(
                suggestions=[Suggestion(type="link_plan", target_id="plan_x", rejected=True)]
            )
        }
    )
    assert apply_defaults(w.repo, rejected, lookup).allocation_origin == "rule:rule_loja"

    assert base.fingerprint is not None
    w.repo.put(
        "annotations",
        Annotation(
            fingerprint=base.fingerprint,
            category_id=FOOD,
            note="presente",
            kind=Kind.FEE,
            allocations=[Share(user_id=ME, pct=Decimal("100"))],
        ),
    )
    by_ann = apply_defaults(w.repo, linked, lookup)
    assert (by_ann.category_id, by_ann.allocation_origin) == (FOOD, "manual")
    assert by_ann.note == "presente"
    assert by_ann.kind is Kind.FEE


@pytest.mark.parametrize(
    "stype, coll, data",
    [
        (
            "link_subscription",
            "subscriptions",
            {
                "id": "sub_x",
                "description": "LOJA X",
                "amount": "50.00",
                "card_id": "card_inter",
                "start_month": "2026-01",
                "category_id": TECH,
                "allocations": HALF,
            },
        ),
        (
            "link_recurring",
            "recurring_purchases",
            {
                "id": "rec_x",
                "description": "LOJA X",
                "estimated_amount": "50.00",
                "every": {"value": 30},
                "last_date": "2026-08-10",
                "card_id": "card_inter",
                "category_id": TECH,
                "allocations": HALF,
            },
        ),
    ],
)
def test_r5_3_level_2_subscription_and_recurring(
    w: World, stype: str, coll: str, data: dict[str, Any]
) -> None:
    w.catalog.create(coll, data)
    tx = staged_tx(w).model_copy(
        update={"review": ReviewInfo(suggestions=[Suggestion(type=stype, target_id=data["id"])])}
    )
    out = apply_defaults(w.repo, tx, last_category_lookup(w.repo))
    prefix = "subscription" if coll == "subscriptions" else "recurring"
    assert (out.category_id, out.allocation_origin) == (TECH, f"{prefix}:{data['id']}")


def test_r5_3_link_to_missing_object_falls_back(w: World) -> None:
    tx = staged_tx(w).model_copy(
        update={"review": ReviewInfo(suggestions=[Suggestion(type="link_plan", target_id="nope")])}
    )
    assert (
        apply_defaults(w.repo, tx, last_category_lookup(w.repo)).allocation_origin == "owners:card"
    )


def test_r5_3_unknown_card_leaves_line_untouched(w: World) -> None:
    tx = staged_tx(w).model_copy(update={"card_id": "card_ghost"})
    assert apply_defaults(w.repo, tx, last_category_lookup(w.repo)) == tx


def test_r10_2_last_category_used_with_same_description(w: World) -> None:
    from expense_tracker.domain.models import Source, Transaction

    for i, (day, cat) in enumerate([(date(2026, 8, 1), FOOD), (date(2026, 9, 1), HOME)]):
        w.repo.put(
            "transactions",
            Transaction(
                id=f"t{i}",
                source=Source(type="manual"),
                card_id="card_inter",
                purchase_date=day,
                invoice_month="2026-09",
                description="Padaria  Sol",
                amount=Decimal("5.00"),
                category_id=cat,
            ),
        )
    lookup = last_category_lookup(w.repo)
    assert lookup("PADARIA SOL") == HOME
    assert lookup("OUTRA") is None
    tx = apply_defaults(w.repo, staged_tx(w, desc="PADARIA SOL", amount="5.00"), lookup)
    assert tx.category_id == HOME


# ------------------------------------------------------------------ stage_document


def test_r5_1_stage_document_marks_missing_category_and_needs_choice(w: World) -> None:
    for pid in ("plan_a", "plan_b"):
        w.catalog.create(
            "installment_plans",
            {
                "id": pid,
                "card_id": "card_inter",
                "description": "LOJA X",
                "total_installments": 10,
                "first_invoice_month": "2026-08",
                "total_amount": "500.00",
                "category_id": TECH,
            },
        )
    res = invoice(
        raw("LOJA X (Parcela 3 de 10)", "50.00", 0, installment_n=3, installment_of=10),
        raw("PADARIA", "5.00", 1),
    )
    ident = identify(w.repo, entry(), res)
    staged, recon = stage_document(w.repo, entry(), res, ident, NOW)
    loja, padaria = staged
    assert loja.review is not None and loja.review.status == "needs_choice"
    assert padaria.review is not None
    assert padaria.review.warnings == ["category_missing"]
    assert padaria.review.status == "pending"
    assert recon.statuses == {loja.id: "needs_choice"}

    # the choice I made is remembered by fingerprint and re-applied on re-staging
    assert loja.fingerprint is not None
    w.repo.put(
        "annotations",
        Annotation(fingerprint=loja.fingerprint, link_choices={"choose_plan": "plan_b"}),
    )
    again, _ = stage_document(w.repo, entry(), res, ident, NOW)
    s = again[0].review.suggestions[0]  # type: ignore[union-attr]
    assert (s.type, s.target_id) == ("choose_plan", "plan_b")
    assert again[0].review.status == "pending"  # type: ignore[union-attr]

    # ``only`` restricts the result to some fingerprints (diff of a changed document)
    sub, _ = stage_document(w.repo, entry(), res, ident, NOW, only={padaria.fingerprint})  # type: ignore[arg-type]
    assert [t.id for t in sub] == [padaria.id]


def test_r5_3_chosen_plan_gives_level_2_defaults(w: World) -> None:
    for pid, cat in (("plan_a", HOME), ("plan_b", TECH)):
        w.catalog.create(
            "installment_plans",
            {
                "id": pid,
                "card_id": "card_inter",
                "description": "LOJA X",
                "total_installments": 10,
                "first_invoice_month": "2026-08",
                "total_amount": "500.00",
                "category_id": cat,
            },
        )
    res = invoice(raw("LOJA X (Parcela 3 de 10)", "50.00", installment_n=3, installment_of=10))
    ident = identify(w.repo, entry(), res)
    [tx], _ = stage_document(w.repo, entry(), res, ident, NOW)
    assert tx.fingerprint is not None
    w.repo.put(
        "annotations",
        Annotation(fingerprint=tx.fingerprint, link_choices={"choose_plan": "plan_b"}),
    )
    [again], _ = stage_document(w.repo, entry(), res, ident, NOW)
    # docs/08 level 2: the chosen plan gives its category; its division only when defined
    assert (again.category_id, again.allocation_origin) == (TECH, "owners:card")


def test_r5_2_rejected_suggestion_is_remembered(w: World) -> None:
    res = invoice(raw("LOJA NOVA (Parcela 1 de 3)", "50.00", installment_n=1, installment_of=3))
    ident = identify(w.repo, entry(), res)
    [tx], _ = stage_document(w.repo, entry(), res, ident, NOW)
    assert tx.fingerprint is not None
    w.repo.put(
        "annotations",
        Annotation(fingerprint=tx.fingerprint, link_choices={"create_plan": "rejected"}),
    )
    [again], _ = stage_document(w.repo, entry(), res, ident, NOW)
    assert again.review is not None and again.review.suggestions[0].rejected is True


# ------------------------------------------------------------------ orphan annotations


def orphan(w: World, **kw: Any) -> None:
    data: dict[str, Any] = {
        "fingerprint": "fp_old",
        "category_id": HOME,
        "description": "MERCADO BOM LTDA",
        "purchase_date": date(2026, 9, 10),
        "amount": Decimal("100.00"),
        "owner_id": "card_inter",
    }
    data.update(kw)
    w.repo.put("annotations", Annotation(**data))


@pytest.mark.parametrize(
    "over, found",
    [
        ({}, True),
        ({"purchase_date": date(2026, 9, 12)}, True),  # ±2 days
        ({"purchase_date": date(2026, 9, 13)}, False),
        ({"amount": Decimal("101.00")}, True),  # ±1%
        ({"amount": Decimal("101.02")}, False),
        ({"description": "MERCADO BOM LTDX"}, True),  # similarity ≥ 0.9
        ({"description": "MERCADINHO"}, False),
        ({"owner_id": "card_other"}, False),
        ({"owner_id": None}, True),
        ({"description": None}, False),
        ({"purchase_date": None}, False),
    ],
)
def test_r3_5_orphan_annotation_suggests_previous_edit(
    w: World, over: dict[str, Any], found: bool
) -> None:
    orphan(w, **over)
    tx = staged_tx(w, desc="MERCADO BOM LTDA", amount="100.00")
    s = orphan_suggestion(w.repo, tx, active_fps=set())
    if found:
        assert s is not None and (s.type, s.target_id) == ("apply_annotation", "fp_old")
    else:
        assert s is None


def test_r3_5_orphan_ignored_when_annotation_is_active_or_line_has_its_own(w: World) -> None:
    orphan(w)
    tx = staged_tx(w, desc="MERCADO BOM LTDA", amount="100.00")
    assert orphan_suggestion(w.repo, tx, active_fps={"fp_old"}) is None
    assert tx.fingerprint is not None
    w.repo.put("annotations", Annotation(fingerprint=tx.fingerprint, category_id=FOOD))
    assert orphan_suggestion(w.repo, tx, active_fps=set()) is None
