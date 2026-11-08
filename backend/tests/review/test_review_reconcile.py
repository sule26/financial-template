"""Reconciliation rules of docs/09 "Reconciliação" (rows 1–15, 7b, 10b) and their order."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from review_builders import (
    ANA,
    ME,
    PAI,
    account,
    card,
    ctx,
    investment,
    invoice_doc,
    line,
    only,
    plan,
    recurring,
    subscription,
    types,
)

from expense_tracker.domain.models import Anticipation, Kind, PaymentMethod
from expense_tracker.review.reconcile import (
    installment_n_for,
    reconcile_invoice,
    reconcile_statement,
)

M = "2026-10"  # invoice month; plan_a (first 2026-08) expects installment 3 here


def inv(c, lines, month=M, card_main="card_a"):  # type: ignore[no-untyped-def]
    return reconcile_invoice(c, lines, month, card_main)


# ------------------------------------------------------------------ rows 1-3


def test_r8_1_installment_links_to_existing_plan() -> None:
    tx = line("LOJA X (Parcela 3 de 10)", "50.00", n=3, of=10)
    r = inv(ctx(plans=[plan()]), [tx])
    s = only(r, tx)
    assert (s.type, s.target_id) == ("link_plan", "plan_a")
    assert r.warnings == []


@pytest.mark.parametrize(
    "amount, n, linked",
    [
        ("50.01", 3, True),  # value ±R$ 0,01
        ("49.99", 3, True),
        ("50.02", 3, False),
        ("50.00", 2, True),  # n expected in the month ±1
        ("50.00", 4, True),
        ("50.00", 5, False),
        ("50.00", 1, False),
    ],
)
def test_r8_1_plan_match_tolerances(amount: str, n: int, linked: bool) -> None:
    tx = line(f"LOJA X (Parcela {n} de 10)", amount, n=n, of=10)
    r = inv(ctx(plans=[plan()]), [tx])
    assert types(r, tx) == (["link_plan"] if linked else ["create_plan"])


@pytest.mark.parametrize(
    "desc, of, card_id",
    [
        ("OUTRA COISA TOTALMENTE (Parcela 3 de 10)", 10, "card_a"),  # description not similar
        ("LOJA X (Parcela 3 de 12)", 12, "card_a"),  # different `of`
        ("LOJA X (Parcela 3 de 10)", 10, "card_b"),  # different card
    ],
)
def test_r8_1_plan_needs_same_card_same_of_and_similar_description(
    desc: str, of: int, card_id: str
) -> None:
    tx = line(desc, "50.00", n=3, of=of, card_id=card_id)
    c = ctx(cards=[card("card_a"), card("card_b")], plans=[plan()])
    r = inv(c, [tx], card_main=card_id)
    assert types(r, tx) == ["create_plan"]


def test_r8_1_installment_on_additional_card_matches_plan_of_main_card() -> None:
    tx = line("LOJA X (Parcela 3 de 10)", "50.00", n=3, of=10, card_id="card_add")
    c = ctx(cards=[card("card_a"), card("card_add", parent="card_a")], plans=[plan()])
    assert types(inv(c, [tx]), tx) == ["link_plan"]


def test_r8_2_installment_without_plan_suggests_creating_it() -> None:
    tx = line("LOJA NOVA (Parcela 4 de 10)", "80.00", n=4, of=10)
    s = only(inv(ctx(), [tx]), tx)
    assert s.type == "create_plan"
    assert s.target_id is None
    # first_invoice_month = month − (n − 1)
    assert s.data == {"n": 4, "of": 10, "first_invoice_month": "2026-07"}


def test_r8_1_two_candidate_plans_need_a_choice() -> None:
    tx = line("LOJA X (Parcela 3 de 10)", "50.00", n=3, of=10)
    plans = [plan("plan_a"), plan("plan_b", desc="LOJA X.")]
    r = inv(ctx(plans=plans), [tx])
    s = only(r, tx)
    assert s.type == "choose_plan"
    assert s.target_id is None
    assert sorted(s.candidates) == ["plan_a", "plan_b"]
    assert r.statuses[tx.id] == "needs_choice"


def test_r8_1_same_installment_of_a_plan_is_not_linked_twice() -> None:
    # two identical purchases in installments: one links, the other is a new plan
    a = line("LOJA X (Parcela 3 de 10)", "50.00", n=3, of=10)
    b = line("LOJA X (Parcela 3 de 10)", "50.00", n=3, of=10)
    r = inv(ctx(plans=[plan()]), [a, b])
    assert types(r, a) == ["link_plan"]
    assert types(r, b) == ["create_plan"]


def test_installment_n_for_counts_from_first_month() -> None:
    assert installment_n_for(plan(first="2026-08"), "2026-10") == 3


# ------------------------------------------------------------------ row 4


def test_r8_7_refund_of_installment_purchase_links_plan_and_never_creates_one() -> None:
    tx = line("LOJA X (Parcela 3 de 10)", "-50.00", n=3, of=10)
    r = inv(ctx(plans=[plan()]), [tx])
    s = only(r, tx)
    assert (s.type, s.target_id) == ("refund_plan", "plan_a")
    assert s.data["cancel_suggested"] is False  # 50 < remaining (7 × 50)
    assert s.data["remaining"] == "350.00"


def test_r8_7_refund_covering_the_remainder_suggests_cancelling() -> None:
    tx = line("ESTORNO LOJA X", "-350.00")
    s = only(inv(ctx(plans=[plan(desc="ESTORNO LOJA X")]), [tx]), tx)
    assert s.type == "refund_plan"
    assert s.data["cancel_suggested"] is True


def test_r8_7_refund_with_installment_and_no_plan_creates_nothing() -> None:
    tx = line("LOJA SEM PLANO (Parcela 1 de 3)", "-30.00", n=1, of=3)
    r = inv(ctx(), [tx])
    assert "create_plan" not in types(r, tx)
    assert types(r, tx) == []


# ------------------------------------------------------------------ rows 5, 6, 8


def ant_plan(**kw):  # type: ignore[no-untyped-def]
    return plan(
        first="2026-02",
        anticipation=Anticipation(from_n=9, target_month=M),
        **kw,
    )


def test_r7_3_anticipated_installments_link_to_the_anticipation() -> None:
    a = line("LOJA X (Parcela 9 de 10)", "50.00", n=9, of=10)
    b = line("LOJA X (Parcela 10 de 10)", "50.00", n=10, of=10)
    r = inv(ctx(plans=[ant_plan()]), [a, b])
    for tx in (a, b):
        s = only(r, tx)
        assert (s.type, s.target_id) == ("link_anticipation", "plan_a")
    assert r.warnings == []


def test_r7_3_anticipation_tagged_line_links_to_the_anticipation() -> None:
    tx = line("Antecipada - LOJA X", "95.00", tag="anticipation")
    s = only(inv(ctx(plans=[ant_plan()]), [tx]), tx)
    assert (s.type, s.target_id) == ("link_anticipation", "plan_a")


def test_r7_5_discount_line_links_to_the_anticipated_plan() -> None:
    tx = line("Desconto Antecipação LOJA X", "-5.00", tag="anticipation_discount")
    s = only(inv(ctx(plans=[ant_plan()]), [tx]), tx)
    assert (s.type, s.target_id) == ("link_anticipation_discount", "plan_a")


def test_r7_5_discount_with_other_description_links_when_single_anticipated_plan() -> None:
    tx = line("CREDITO DIVERSO 123", "-5.00", tag="anticipation_discount")
    s = only(inv(ctx(plans=[ant_plan()]), [tx]), tx)
    assert (s.type, s.target_id) == ("link_anticipation_discount", "plan_a")


def test_r7_5_discount_is_not_guessed_between_two_anticipated_plans() -> None:
    tx = line("CREDITO DIVERSO 123", "-5.00", tag="anticipation_discount")
    plans = [ant_plan(), ant_plan(pid="plan_b", desc="OUTRA LOJA ZZZ")]
    assert "link_anticipation_discount" not in types(inv(ctx(plans=plans), [tx]), tx)


def test_r7_3_anticipation_of_another_month_does_not_capture_lines() -> None:
    p = plan(first="2026-02", anticipation=Anticipation(from_n=9, target_month="2026-12"))
    tx = line("LOJA X (Parcela 9 de 10)", "50.00", n=9, of=10)
    assert types(inv(ctx(plans=[p]), [tx]), tx) == ["link_plan"]


def test_r7_3_installment_after_target_month_warns_anticipation_did_not_happen() -> None:
    # row 8: anticipation registered for 2026-09, but installment 9 still came in 2026-10
    p = plan(first="2026-02", anticipation=Anticipation(from_n=9, target_month="2026-09"))
    tx = line("LOJA X (Parcela 9 de 10)", "50.00", n=9, of=10)
    r = inv(ctx(plans=[p]), [tx])
    assert types(r, tx) == ["link_plan"]
    assert "anticipation_not_happened:plan_a" in r.warnings


# ------------------------------------------------------------------ rows 7, 7b


def test_r8_8_missing_expected_installment_warns() -> None:
    other = line("PADARIA", "10.00")
    r = inv(ctx(plans=[plan()]), [other])
    assert r.warnings == ["expected_installment_missing:plan_a:3"]


def test_r8_8_no_warning_for_a_cancelled_plan_or_another_card() -> None:
    from expense_tracker.domain.models import StatusOverride

    p1 = plan(status_override=StatusOverride(from_n=3))
    p2 = plan("plan_b", card_id="card_b")
    c = ctx(cards=[card("card_a"), card("card_b")], plans=[p1, p2])
    assert inv(c, [line("PADARIA", "10.00")]).warnings == []


def test_r8_8_two_installments_of_existing_plan_suggest_bank_anticipation() -> None:
    # row 7b: plan expects 3/10 in the month, the invoice has 03/10 and 04/10
    a = line("LOJA X (Parcela 3 de 10)", "50.00", n=3, of=10)
    b = line("LOJA X (Parcela 4 de 10)", "50.00", n=4, of=10)
    r = inv(ctx(plans=[plan()]), [a, b])
    assert types(r, a) == ["link_plan"]
    s = only(r, b)
    assert (s.type, s.target_id) == ("bank_anticipation", "plan_a")
    assert s.data["from_n"] == 4
    assert r.warnings == []


def test_r8_8_two_installments_without_plan_create_plan_and_bank_anticipation() -> None:
    a = line("LOJA Z (Parcela 9 de 10)", "30.00", n=9, of=10)
    b = line("LOJA Z (Parcela 10 de 10)", "30.00", n=10, of=10)
    r = inv(ctx(), [a, b])
    sa, sb = only(r, a), only(r, b)
    assert sa.type == "create_plan"
    assert sb.type == "bank_anticipation"
    assert sb.target_id is None
    assert sb.data["plan_fingerprint"] == a.fingerprint  # the new plan is derived from line 9
    assert sb.data["from_n"] == 10


def test_r8_8_single_installment_is_not_a_bank_anticipation() -> None:
    a = line("LOJA Z (Parcela 9 de 10)", "30.00", n=9, of=10)
    b = line("OUTRA (Parcela 2 de 3)", "70.00", n=2, of=3)
    r = inv(ctx(), [a, b])
    assert types(r, a) == ["create_plan"]
    assert types(r, b) == ["create_plan"]


# ------------------------------------------------------------------ rows 9, 10


def manual(desc: str = "MERCADO BOM", amount: str = "100.00", day: date = date(2026, 9, 10), **kw):  # type: ignore[no-untyped-def]
    kw.setdefault("tid", f"man_{desc}_{amount}_{day}")
    return line(desc, amount, day=day, source="manual", provisional=True, **kw)


@pytest.mark.parametrize(
    "amount, day, desc, matched",
    [
        ("100.00", date(2026, 9, 10), "MERCADO BOM", True),
        ("101.00", date(2026, 9, 13), "MERCADO BOM", True),  # ±1%, ±3 days
        ("101.02", date(2026, 9, 10), "MERCADO BOM", False),
        ("100.00", date(2026, 9, 14), "MERCADO BOM", False),
        ("100.00", date(2026, 9, 6), "MERCADO BOM", False),
        ("100.00", date(2026, 9, 11), "MERC", False),  # similarity < 0.6 and not exact
        ("100.00", date(2026, 9, 10), "MERC", True),  # ≥ 0.3 with exact value and date
    ],
)
def test_r10_3_manual_match_criteria(amount: str, day: date, desc: str, matched: bool) -> None:
    tx = line("MERCADO BOM LTDA", amount, day=day)
    m = manual(desc=desc)
    r = inv(ctx(manuals=[m]), [tx])
    assert types(r, tx) == (["match_manual"] if matched else [])
    assert (f"unmatched_manual:{m.id}" in r.warnings) is not matched


def test_r10_3_manual_needs_same_card() -> None:
    tx = line("MERCADO BOM", "100.00")
    m = manual(card_id="card_b")
    c = ctx(cards=[card("card_a"), card("card_b")], manuals=[m])
    assert types(inv(c, [tx]), tx) == []


def test_r10_3_manual_invoice_month_within_one() -> None:
    tx = line("MERCADO BOM", "100.00")
    m = manual(month="2026-08")
    assert types(inv(ctx(manuals=[m]), [tx]), tx) == []


def test_r10_3_each_manual_matches_at_most_one_line() -> None:
    a = line("MERCADO BOM", "100.00")
    b = line("MERCADO BOM", "100.00")
    m = manual()
    r = inv(ctx(manuals=[m]), [a, b])
    assert types(r, a) == ["match_manual"]
    assert types(r, b) == []
    assert r.warnings == []


def test_r10_3_tie_between_two_manuals_needs_a_choice() -> None:
    tx = line("MERCADO BOM", "100.00")
    m1 = manual(tid="man_1")
    m2 = manual(tid="man_2")
    r = inv(ctx(manuals=[m1, m2]), [tx])
    assert r.statuses.get(tx.id) == "needs_choice"


def test_r10_3_unmatched_manual_of_other_month_or_card_is_not_reported() -> None:
    m1 = manual(month="2026-11")
    m2 = manual(card_id="card_b", tid="man_b")
    c = ctx(cards=[card("card_a"), card("card_b")], manuals=[m1, m2])
    assert inv(c, [line("PADARIA", "5.00")]).warnings == []


# ------------------------------------------------------------------ row 10b


def test_r12_3_purchase_links_to_recurring_occurrence() -> None:
    # every 45 days from 2026-08-01 -> 2026-09-15 (tolerance ±15 days)
    tx = line("RACAO PET SHOP", "210.00", day=date(2026, 9, 25))
    s = only(inv(ctx(recurring=[recurring()]), [tx]), tx)
    assert (s.type, s.target_id) == ("link_recurring", "rec_a")


@pytest.mark.parametrize(
    "amount, day, ok",
    [
        ("240.00", date(2026, 9, 15), True),  # +20%
        ("240.01", date(2026, 9, 15), False),
        ("200.00", date(2026, 8, 31), True),  # −15 days
        ("200.00", date(2026, 8, 30), False),
        ("200.00", date(2026, 9, 30), True),  # +15 days
        ("200.00", date(2026, 10, 1), False),
    ],
)
def test_r12_3_recurring_tolerances(amount: str, day: date, ok: bool) -> None:
    tx = line("RACAO PET", amount, day=day)
    assert types(inv(ctx(recurring=[recurring()]), [tx]), tx) == (["link_recurring"] if ok else [])


def test_r12_3_match_description_regex_is_enough() -> None:
    rec = recurring(desc="Ração do Rex", match_description="PETZ")
    tx = line("PETZ COMERCIO 0042", "190.00", day=date(2026, 9, 16))
    assert types(inv(ctx(recurring=[rec]), [tx]), tx) == ["link_recurring"]


def test_r12_3_inactive_recurring_is_ignored() -> None:
    rec = recurring(active=False)
    tx = line("RACAO PET", "200.00", day=date(2026, 9, 15))
    assert types(inv(ctx(recurring=[rec]), [tx]), tx) == []


def test_r12_3_manual_and_recurring_both_apply() -> None:
    # 9 + 10b: the provisional manual is absorbed and the line keeps the recurring link
    tx = line("RACAO PET", "200.00", day=date(2026, 9, 15))
    m = manual(desc="RACAO PET", amount="200.00", day=date(2026, 9, 15))
    r = inv(ctx(manuals=[m], recurring=[recurring()]), [tx])
    assert types(r, tx) == ["match_manual", "link_recurring"]


# ------------------------------------------------------------------ row 11


def test_r8_3_charge_links_to_subscription() -> None:
    tx = line("STREAMING", "40.00")
    s = only(inv(ctx(subscriptions=[subscription()]), [tx]), tx)
    assert (s.type, s.target_id) == ("link_subscription", "sub_a")
    assert s.data["adjust"] is None


def test_r8_3_price_change_within_5_percent_suggests_adjustment() -> None:
    tx = line("STREAMING", "42.00")
    s = only(inv(ctx(subscriptions=[subscription()]), [tx]), tx)
    assert s.type == "link_subscription"
    assert s.data["adjust"] == "42.00"


@pytest.mark.parametrize(
    "amount, sub_kw",
    [
        ("42.01", {}),  # > 5%
        ("40.00", {"card_id": "card_b"}),
        ("40.00", {"end_month": "2026-09"}),
    ],
)
def test_r8_3_subscription_mismatch(amount: str, sub_kw: dict[str, str]) -> None:
    tx = line("STREAMING", amount)
    c = ctx(cards=[card("card_a"), card("card_b")], subscriptions=[subscription(**sub_kw)])
    assert types(inv(c, [tx]), tx) == []


def test_order_manual_wins_over_subscription() -> None:
    tx = line("STREAMING", "40.00")
    m = manual(desc="STREAMING", amount="40.00")
    r = inv(ctx(manuals=[m], subscriptions=[subscription()]), [tx])
    assert types(r, tx) == ["match_manual"]


def test_order_refund_wins_over_installment_link() -> None:
    # row 4 is applied before row 1
    tx = line("LOJA X (Parcela 3 de 10)", "-50.00", n=3, of=10)
    assert types(inv(ctx(plans=[plan()]), [tx]), tx) == ["refund_plan"]


def test_order_anticipation_wins_over_plan_link() -> None:
    # row 5 before row 1: 9/10 is part of the anticipation, not a regular installment
    tx = line("LOJA X (Parcela 9 de 10)", "50.00", n=9, of=10)
    assert types(inv(ctx(plans=[ant_plan()]), [tx]), tx) == ["link_anticipation"]


# ------------------------------------------------------------------ row 15 on invoices


def test_r9_4_investment_charged_on_card_links_single_investment() -> None:
    tx = line("PREVIDENCIA XP", "300.00", tag="investment_contribution")
    s = only(inv(ctx(investments=[investment()]), [tx]), tx)
    assert (s.type, s.target_id) == ("link_investment", "inv_a")
    assert s.data["movement"] == "contribution"


def test_r9_4_investment_on_card_with_several_investments_asks() -> None:
    tx = line("PREVIDENCIA XP", "300.00", tag="investment_contribution")
    s = only(inv(ctx(investments=[investment("inv_a"), investment("inv_b")]), [tx]), tx)
    assert s.type == "choose_investment"
    assert s.candidates == ["inv_a", "inv_b"]


# ================================================================== statements


def st(c, lines, acc="acc_a"):  # type: ignore[no-untyped-def]
    return reconcile_statement(c, lines, acc)


def sline(desc: str, amount: str, day: date = date(2026, 9, 12), **kw):  # type: ignore[no-untyped-def]
    kw.setdefault("account_id", "acc_a")
    kw.setdefault("month", "2026-09")
    return line(desc, amount, day=day, card_id=None, **kw)


@pytest.mark.parametrize(
    "day, ok",
    [
        (date(2026, 9, 5), True),  # due − 10
        (date(2026, 9, 4), False),
        (date(2026, 9, 22), True),  # due + 7
        (date(2026, 9, 23), False),
    ],
)
def test_r8_4_invoice_payment_window(day: date, ok: bool) -> None:
    tx = sline("PAGTO CARTAO", "500.00", day=day, kind=Kind.TRANSFER)
    r = st(ctx(invoices=[invoice_doc()]), [tx])
    if ok:
        s = only(r, tx)
        assert (s.type, s.target_id) == ("invoice_payment", "faturas/a.pdf")
        assert s.data == {"card_id": "card_a", "invoice_month": "2026-09"}
    else:
        assert "invoice_payment" not in types(r, tx)


@pytest.mark.parametrize("amount, ok", [("500.01", True), ("499.99", True), ("500.02", False)])
def test_r8_4_invoice_payment_amount_due_tolerance(amount: str, ok: bool) -> None:
    tx = sline("PAGTO CARTAO", amount, kind=Kind.TRANSFER)
    r = st(ctx(invoices=[invoice_doc()]), [tx])
    assert ("invoice_payment" in types(r, tx)) is ok


def test_r8_4_advance_payment_matches_when_sum_equals_total_minus_due() -> None:
    # paid in advance: amount_due 0, payment of the whole total before the due date
    doc = invoice_doc(amount_due="0.00")
    tx = sline(
        "PAGAMENTO FATURA",
        "500.00",
        day=date(2026, 8, 20),
        kind=Kind.TRANSFER,
        tag="invoice_payment",
    )
    assert types(st(ctx(invoices=[doc]), [tx]), tx) == ["invoice_payment"]


@pytest.mark.parametrize(
    "amount_due, amount, day",
    [
        ("0.00", "100.00", date(2026, 8, 20)),  # Σ 100 ≠ 500 − 0
        ("500.00", "500.00", date(2026, 9, 4)),  # outside [due − 10, due + 7]; 500 − 500 = 0
    ],
)
def test_r8_4_advance_payment_with_wrong_sum_does_not_match(
    amount_due: str, amount: str, day: date
) -> None:
    doc = invoice_doc(amount_due=amount_due)
    tx = sline("PAGAMENTO FATURA", amount, day=day, kind=Kind.TRANSFER, tag="invoice_payment")
    assert "invoice_payment" not in types(st(ctx(invoices=[doc]), [tx]), tx)


def test_r8_4_invoice_with_nothing_due_does_not_expect_payment_by_due_date() -> None:
    doc = invoice_doc(amount_due="0.00", closing=None)
    tx = sline("PAGTO CARTAO", "0.00", kind=Kind.TRANSFER)
    assert types(st(ctx(invoices=[doc]), [tx]), tx) == []


def test_r8_4_invoice_without_due_date_is_skipped() -> None:
    tx = sline("PAGAMENTO FATURA", "500.00", kind=Kind.TRANSFER, tag="invoice_payment")
    assert types(st(ctx(invoices=[invoice_doc(due=None)]), [tx]), tx) == []


def test_r8_10_transfer_between_my_accounts() -> None:
    out = sline("TED CONTA CONJUNTA", "300.00", kind=Kind.TRANSFER, method=PaymentMethod.TRANSFER)
    inn = sline(
        "TED RECEBIDA",
        "-300.00",
        account_id="acc_b",
        kind=Kind.TRANSFER,
        method=PaymentMethod.TRANSFER,
        day=date(2026, 9, 14),
    )
    c = ctx(accounts=[account("acc_a"), account("acc_b")], other_lines=[inn])
    s = only(st(c, [out]), out)
    assert (s.type, s.target_id) == ("internal_transfer", inn.id)
    assert s.data["fingerprint"] == inn.fingerprint


def test_r8_10_transfer_needs_two_days_and_same_value() -> None:
    out = sline("TED", "300.00", kind=Kind.TRANSFER, method=PaymentMethod.TRANSFER)
    late = sline(
        "TED",
        "-300.00",
        account_id="acc_b",
        kind=Kind.TRANSFER,
        day=date(2026, 9, 15),
        method=PaymentMethod.TRANSFER,
    )
    other_value = sline(
        "TED", "-299.00", account_id="acc_b", kind=Kind.TRANSFER, method=PaymentMethod.TRANSFER
    )
    same_acc = sline("TED", "-300.00", kind=Kind.TRANSFER, method=PaymentMethod.TRANSFER)
    c = ctx(
        accounts=[account("acc_a"), account("acc_b")], other_lines=[late, other_value, same_acc]
    )
    assert types(st(c, [out]), out) == []


def test_r8_10_pix_out_and_income_in_are_an_internal_transfer() -> None:
    out = sline("PIX ENVIADO CONTA CONJUNTA", "300.00", method=PaymentMethod.PIX)
    inn = sline(
        "PIX RECEBIDO FULANO",
        "300.00",
        account_id="acc_b",
        kind=Kind.INCOME,
        method=PaymentMethod.TRANSFER,
    )
    c = ctx(accounts=[account("acc_a"), account("acc_b")], other_lines=[inn])
    assert types(st(c, [out]), out) == ["internal_transfer"]


def test_r6_6_credit_from_a_person_suggests_settlement() -> None:
    tx = sline("PIX RECEBIDO JOSE DA SILVA", "200.00", kind=Kind.INCOME)
    s = only(st(ctx(), [tx]), tx)
    assert (s.type, s.target_id) == ("settlement", PAI)
    assert s.data["to_user_id"] == ME


def test_r6_6_alias_of_the_account_responsible_is_not_a_settlement() -> None:
    from expense_tracker.domain.models import User

    users = [User(id=ME, name="Eu", aliases=["FULANO DE TAL"]), User(id=ANA, name="Ana")]
    tx = sline("PIX RECEBIDO FULANO DE TAL", "200.00", kind=Kind.INCOME)
    assert types(st(ctx(users=users), [tx]), tx) == []


def test_r6_6_unknown_sender_is_plain_income() -> None:
    tx = sline("PIX RECEBIDO EMPRESA XYZ", "200.00", kind=Kind.INCOME)
    assert types(st(ctx(), [tx]), tx) == []


@pytest.mark.parametrize(
    "tag, movement",
    [("investment_contribution", "contribution"), ("investment_withdrawal", "withdrawal")],
)
def test_r9_4_statement_investment_of_the_account(tag: str, movement: str) -> None:
    tx = sline("APLICACAO CDB", "300.00", kind=Kind.TRANSFER, tag=tag)
    invs = [investment("inv_other"), investment("inv_a", account_id="acc_a")]
    s = only(st(ctx(investments=invs), [tx]), tx)
    assert (s.type, s.target_id) == ("link_investment", "inv_a")
    assert s.data["movement"] == movement


def test_r9_4_statement_investment_ambiguous_needs_choice() -> None:
    tx = sline("APLICACAO CDB", "300.00", kind=Kind.TRANSFER, tag="investment_contribution")
    r = st(ctx(investments=[investment("inv_a"), investment("inv_b")]), [tx])
    assert only(r, tx).type == "choose_investment"
    assert r.statuses[tx.id] == "needs_choice"


def test_r9_4_closed_or_no_investment() -> None:
    tx = sline("APLICACAO CDB", "300.00", kind=Kind.TRANSFER, tag="investment_contribution")
    closed = investment("inv_a", account_id="acc_a", closed_at=date(2026, 1, 1))
    assert types(st(ctx(investments=[closed]), [tx]), tx) == []


def test_r10_3_statement_manual_match_and_unmatched_warning() -> None:
    tx = sline("PADARIA SOL", "12.00")
    m_ok = manual(
        desc="PADARIA SOL",
        amount="12.00",
        day=date(2026, 9, 12),
        card_id=None,
        account_id="acc_a",
        method=PaymentMethod.PIX,
        month="2026-09",
    )
    m_miss = manual(
        desc="FEIRA",
        amount="30.00",
        day=date(2026, 9, 12),
        card_id=None,
        account_id="acc_a",
        method=PaymentMethod.PIX,
        month="2026-09",
    )
    m_out = manual(
        desc="FEIRA",
        amount="30.00",
        day=date(2026, 9, 25),
        card_id=None,
        account_id="acc_a",
        method=PaymentMethod.PIX,
        month="2026-09",
    )
    r = st(ctx(manuals=[m_ok, m_miss, m_out]), [tx])
    assert types(r, tx) == ["match_manual"]
    # only manuals inside the statement's date range are reported
    assert r.warnings == [f"unmatched_manual:{m_miss.id}"]


def test_r12_3_statement_recurring_and_subscription() -> None:
    rec = recurring(card_id=None, account_id="acc_a", payment_method=PaymentMethod.DEBIT)
    sub = subscription(
        card_id=None, account_id="acc_a", payment_method=PaymentMethod.DEBIT, desc="ACADEMIA"
    )
    a = sline("RACAO PET", "200.00", day=date(2026, 9, 15))
    b = sline("ACADEMIA", "40.00")
    r = st(ctx(recurring=[rec], subscriptions=[sub]), [a, b])
    assert types(r, a) == ["link_recurring"]
    assert types(r, b) == ["link_subscription"]


def test_statement_credit_without_match_has_no_suggestion() -> None:
    tx = sline("ESTORNO TARIFA", "-5.00", kind=Kind.TRANSFER)
    assert types(st(ctx(), [tx]), tx) == []


def test_statement_unknown_account_and_empty_document() -> None:
    assert st(ctx(), [], acc="acc_x").warnings == []
    tx = sline("PIX RECEBIDO JOSE DA SILVA", "10.00", kind=Kind.INCOME, account_id="acc_x")
    # without the account there is no responsible user to settle with
    assert types(st(ctx(), [tx], acc="acc_x"), tx) == []


def test_r8_7_installment_charged_amount_is_decimal() -> None:
    # guard: the suggestion data is JSON-safe (money as strings)
    tx = line("LOJA X (Parcela 3 de 10)", "-50.00", n=3, of=10)
    s = only(inv(ctx(plans=[plan()]), [tx]), tx)
    assert isinstance(s.data["remaining"], str)
    assert Decimal(s.data["remaining"]) == Decimal("350.00")
