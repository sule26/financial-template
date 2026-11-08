"""Ledger: real x projected per (card, month) and (account, month) (docs/07 "Real x projetado").

Fixed "today" is 2026-10-12; card_x closes on the 3rd and is due on the 10th, so
``H(card_x) = 2026-11`` and every month ``< 2026-11`` is already past.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from builders import ANA, EU, Builders

from expense_tracker.domain.allocation import AllocationError
from expense_tracker.domain.installments import anticipate
from expense_tracker.domain.ledger import (
    DocumentInfo,
    Ledger,
    LedgerItem,
    projection_months,
    spending_total,
)
from expense_tracker.domain.models import Kind, PaymentMethod

D = Decimal
mk = Builders
TODAY = date(2026, 10, 12)
CARD = mk.card("card_x", 3, 10)


def refs(items: list[LedgerItem]) -> list[str]:
    return sorted(i.ref_id for i in items)


def card_world(**extra: object) -> dict[str, object]:
    """A card with one of each forecast source in 2026-12 plus a provisional manual."""
    world: dict[str, object] = {
        "cards": [CARD],
        "plans": [mk.plan("plan_1", n=3, total=300, first="2026-11")],
        "subscriptions": [mk.subscription("sub_1", 50, start="2026-01")],
        "recurring": [mk.recurring("rec_racao", last=date(2026, 9, 20))],  # 11-04 -> 2026-12
        "transactions": [
            mk.tx("tx_manual", 80, month="2026-12", day=date(2026, 11, 20), card="card_x",
                  manual=True),
            mk.tx("tx_import", 120, month="2026-12", day=date(2026, 11, 15), card="card_x",
                  sha="sha_dec"),
        ],
    }  # fmt: skip
    world.update(extra)
    return world


# ---------------------------------------------------------------- cards


def test_r8_5_month_without_document_uses_projection() -> None:
    # docs/07#real-x-projetado: schedule(plans) + subscriptions + recurring + provisional manuals
    ledger = mk.ledger(TODAY, **card_world())
    state, items = ledger.card_month("card_x", "2026-12")
    assert state == "projected"
    assert refs(items) == ["plan_1", "rec_racao", "sub_1", "tx_manual"]
    origins = {i.ref_id: i.origin for i in items}
    assert origins == {
        "plan_1": "plan",
        "sub_1": "subscription",
        "rec_racao": "recurring",
        "tx_manual": "transaction",
    }
    assert next(i for i in items if i.ref_id == "rec_racao").purchase_date == date(2026, 11, 4)
    assert all(i.responsible_user_id == EU for i in items)


def test_r8_5_month_with_active_document_uses_only_its_transactions() -> None:
    doc = mk.invoice("sha_dec", "2026-12", status="confirmed")
    ledger = mk.ledger(TODAY, **card_world(documents=[doc]))
    state, items = ledger.card_month("card_x", "2026-12")
    assert state == "real"
    assert refs(items) == ["tx_import"]
    assert spending_total(items) == D("120.00")


def test_r8_5_pending_review_invoice_with_confirmed_filter_stays_projected() -> None:
    # docs/07: with the default "only confirmed" filter a document still in review does not zero
    # the month: it stays projected until something is confirmed.
    doc = mk.invoice("sha_dec", "2026-12", status="pending_review")
    staged = mk.tx("stg_1", 999, month="2026-12", day=date(2026, 11, 15), card="card_x",
                   sha="sha_dec")  # fmt: skip
    ledger = mk.ledger(TODAY, **card_world(documents=[doc], staging=[staged]))
    state, items = ledger.card_month("card_x", "2026-12")
    assert state == "projected"
    assert refs(items) == ["plan_1", "rec_racao", "sub_1", "tx_manual"]


def test_r5_5_pending_review_invoice_with_pending_filter_uses_staging() -> None:
    doc = mk.invoice("sha_dec", "2026-12", status="pending_review")
    staged = [
        mk.tx("stg_1", 999, month="2026-12", day=date(2026, 11, 15), card="card_x", sha="sha_dec"),
        mk.tx("stg_overlap", 5, month="2026-12", day=date(2026, 11, 15), card="card_x",
              sha="sha_dec", review_status="overlap"),
        mk.tx("stg_other", 7, month="2026-12", day=date(2026, 11, 15), card="card_x",
              sha="sha_other"),
    ]  # fmt: skip
    ledger = mk.ledger(TODAY, include_pending=True, **card_world(documents=[doc], staging=staged))
    state, items = ledger.card_month("card_x", "2026-12")
    assert state == "real"
    assert refs(items) == ["stg_1", "tx_import"]
    assert {i.ref_id: i.origin for i in items}["stg_1"] == "staging"


def test_r8_5_partially_confirmed_invoice_with_confirmed_filter_uses_only_confirmed() -> None:
    doc = mk.invoice("sha_dec", "2026-12", status="partially_confirmed")
    staged = mk.tx("stg_1", 999, month="2026-12", day=date(2026, 11, 15), card="card_x",
                   sha="sha_dec")  # fmt: skip
    ledger = mk.ledger(TODAY, **card_world(documents=[doc], staging=[staged]))
    state, items = ledger.card_month("card_x", "2026-12")
    assert (state, refs(items)) == ("real", ["tx_import"])


def test_r8_5_inactive_document_is_ignored() -> None:
    doc = mk.invoice("sha_dec", "2026-12", status="superseded")
    ledger = mk.ledger(TODAY, **card_world(documents=[doc]))
    state, _ = ledger.card_month("card_x", "2026-12")
    assert state == "projected"
    assert ledger.document_for("card_x", "2026-12") is None


def test_r4_11_open_invoice_adds_provisionals_and_occurrences_after_as_of() -> None:
    # docs/07: open invoice -> doc items + provisional manuals and planned occurrences after as_of
    doc = mk.invoice("sha_dec", "2026-12", open_invoice=True, as_of=date(2026, 11, 10))
    world = card_world(documents=[doc])
    world["transactions"] = [  # type: ignore[index]
        *world["transactions"],  # type: ignore[misc]
        mk.tx("tx_manual_old", 30, month="2026-12", day=date(2026, 11, 2), card="card_x",
              manual=True),
    ]  # fmt: skip
    world["recurring"] = [
        mk.recurring("rec_before", last=date(2026, 9, 20)),  # 11-04 <= as_of
        mk.recurring("rec_after", last=date(2026, 9, 26)),  # 11-10 not > as_of
        mk.recurring("rec_late", last=date(2026, 9, 28)),  # 11-12 > as_of -> 2026-12
    ]
    ledger = mk.ledger(TODAY, **world)
    state, items = ledger.card_month("card_x", "2026-12")
    assert state == "open"
    # plans and subscriptions are part of the real document; manual 11-20 and rec 11-12 are after
    assert refs(items) == ["rec_late", "tx_import", "tx_manual"]


def test_r4_11_open_invoice_without_as_of_uses_today() -> None:
    doc = mk.invoice("sha_nov", "2026-11", open_invoice=True)
    txs = [
        mk.tx("tx_before", 10, month="2026-11", day=date(2026, 10, 12), card="card_x", manual=True),
        mk.tx("tx_after", 20, month="2026-11", day=date(2026, 10, 13), card="card_x", manual=True),
    ]
    ledger = mk.ledger(TODAY, cards=[CARD], transactions=txs, documents=[doc])
    state, items = ledger.card_month("card_x", "2026-11")
    assert (state, refs(items)) == ("open", ["tx_after"])


def test_r8_9_past_month_without_document_is_missing() -> None:
    # docs/07#mês-faltando-r89: M < H(card) without an active document -> "faltando"
    sub = mk.subscription("sub_1", 50, start="2026-01")
    ledger = mk.ledger(TODAY, cards=[CARD], subscriptions=[sub])
    assert ledger.card_h("card_x") == "2026-11"
    state, items = ledger.card_month("card_x", "2026-09")
    assert state == "missing"
    assert refs(items) == ["sub_1"]  # shows the projection
    assert ledger.card_month("card_x", "2026-11")[0] == "projected"


def test_r8_9_past_month_with_document_is_real() -> None:
    doc = mk.invoice("sha_sep", "2026-09")
    ledger = mk.ledger(TODAY, cards=[CARD], documents=[doc])
    assert ledger.card_month("card_x", "2026-09")[0] == "real"


def test_r8_9_past_month_with_pending_review_invoice_is_not_missing() -> None:
    doc = mk.invoice("sha_sep", "2026-09", status="pending_review")
    ledger = mk.ledger(TODAY, cards=[CARD], documents=[doc])
    assert ledger.card_month("card_x", "2026-09")[0] != "missing"


def test_r10_4_definitive_manual_card_transaction_always_counts() -> None:
    tx = mk.tx("tx_def", 15, month="2026-12", day=date(2026, 11, 20), card="card_x", manual=True,
               provisional=False)  # fmt: skip
    doc = mk.invoice("sha_dec", "2026-12")
    ledger = mk.ledger(TODAY, cards=[CARD], transactions=[tx], documents=[doc])
    assert refs(ledger.card_month("card_x", "2026-12")[1]) == ["tx_def"]


def test_r7_1_anticipation_charge_in_projection_with_description() -> None:
    plan = anticipate(mk.plan("plan_12", n=10, total=1500, first="2026-08"),
                      current_month="2026-11", imported_months=set(), from_n=6,
                      target_month="2026-12")  # fmt: skip
    ledger = mk.ledger(TODAY, cards=[CARD], plans=[plan])
    _, items = ledger.card_month("card_x", "2026-12")
    ant = next(i for i in items if i.origin == "anticipation")
    assert ant.description == "Antecipação LOJA X (6–10/10)"
    assert ant.amount == D("750.00") and ant.is_forecast
    assert ledger.card_month("card_x", "2027-01")[1] == []


def test_r1_10_additional_card_items_bill_on_main_card() -> None:
    extra = mk.card("card_add", parent="card_x", owners=mk.shares((ANA, 100)), responsible=None)
    plan = mk.plan("plan_add", n=1, total=40, first="2026-12", card="card_add")
    sub = mk.subscription("sub_add", 10, card="card_add")
    rec = mk.recurring("rec_add", card="card_add")
    txs = [
        mk.tx("tx_add", 25, month="2026-12", day=date(2026, 11, 20), card="card_add", manual=True),
        mk.tx("tx_other", 1, month="2026-12", day=date(2026, 11, 20), card="card_y", manual=True),
    ]
    other = mk.card("card_y", 25, 5)
    ledger = mk.ledger(TODAY, cards=[CARD, extra, other], plans=[plan], subscriptions=[sub],
                       recurring=[rec], transactions=txs)  # fmt: skip
    _, items = ledger.card_month("card_x", "2026-12")
    assert refs(items) == ["plan_add", "rec_add", "sub_add", "tx_add"]
    item = next(i for i in items if i.ref_id == "tx_add")
    assert item.owners == mk.shares((ANA, 100)) and item.responsible_user_id == EU
    assert ledger.card_h("card_add") == "2026-11"
    view = ledger.month("2026-12")
    assert set(view.states) == {"card_x", "card_y"}


def test_month_for_card_date_uses_actual_closing_of_imported_invoice() -> None:
    doc = mk.invoice("sha_oct", "2026-10", closing_date=date(2026, 10, 5))
    ledger = mk.ledger(TODAY, cards=[CARD], documents=[doc])
    assert ledger.month_for_card_date("card_x", date(2026, 10, 4)) == "2026-10"
    assert mk.ledger(TODAY, cards=[CARD]).month_for_card_date("card_x", date(2026, 10, 4)) == (
        "2026-11"
    )
    assert ledger.billing("card_x") == list(CARD.billing_history)


def test_items_with_unresolvable_ownership_are_dropped() -> None:
    orphan = mk.card("card_orphan", account="acc_ghost", responsible=None)
    tx = mk.tx("tx_o", 10, month="2026-12", day=date(2026, 11, 20), card="card_orphan",
               manual=True)  # fmt: skip
    plan = mk.plan("plan_o", n=1, total=10, first="2026-12", card="card_orphan")
    ledger = mk.ledger(TODAY, cards=[CARD, orphan], transactions=[tx], plans=[plan])
    assert ledger.card_month("card_orphan", "2026-12")[1] == []
    with pytest.raises(AllocationError):
        ledger.card_ownership("card_unknown")
    with pytest.raises(AllocationError):
        ledger.account_ownership("acc_unknown")
    assert ledger.main_card("card_unknown") == "card_unknown"


# ---------------------------------------------------------------- accounts


ACC = mk.account("acc_x")


def acc_tx(tid: str, amount: int, day: date, **kw: object) -> object:
    return mk.tx(tid, amount, month=f"{day.year:04d}-{day.month:02d}", day=day,
                 account="acc_x", **kw)  # type: ignore[arg-type]  # fmt: skip


def test_r8_5_statement_covering_whole_month_uses_only_real() -> None:
    # docs/07: for accounts the "document" is a statement whose period covers the whole month
    stmt = mk.statement("sha_st", "acc_x", date(2026, 9, 1), date(2026, 9, 30))
    txs = [
        acc_tx("tx_imp", 100, date(2026, 9, 10), sha="sha_st"),
        acc_tx("tx_manual", 50, date(2026, 9, 12), manual=True),
    ]
    sub = mk.subscription("sub_acc", 30, card=None, account="acc_x", method=PaymentMethod.DEBIT)
    rec = mk.recurring("rec_acc", last=date(2026, 8, 20), every=20, card=None, account="acc_x",
                       method=PaymentMethod.PIX)  # fmt: skip
    ledger = mk.ledger(TODAY, accounts=[ACC], transactions=txs, documents=[stmt],
                       subscriptions=[sub], recurring=[rec])  # fmt: skip
    state, items = ledger.account_month("acc_x", "2026-09")
    assert (state, refs(items)) == ("real", ["tx_imp"])


def test_r8_5_statement_covering_part_of_month_uses_manuals_for_uncovered_days() -> None:
    stmt = mk.statement("sha_st", "acc_x", date(2026, 9, 1), date(2026, 9, 15))
    txs = [
        acc_tx("tx_imp", 100, date(2026, 9, 10), sha="sha_st"),
        acc_tx("tx_manual_covered", 50, date(2026, 9, 12), manual=True),
        acc_tx("tx_manual_uncovered", 60, date(2026, 9, 20), manual=True),
    ]
    sub = mk.subscription("sub_acc", 30, card=None, account="acc_x", method=PaymentMethod.DEBIT)
    rec = mk.recurring("rec_acc", last=date(2026, 8, 20), every=20, card=None, account="acc_x",
                       method=PaymentMethod.PIX)  # 09-09 (covered), 09-29 (uncovered)  # fmt: skip
    ledger = mk.ledger(TODAY, accounts=[ACC], transactions=txs, documents=[stmt],
                       subscriptions=[sub], recurring=[rec])  # fmt: skip
    state, items = ledger.account_month("acc_x", "2026-09")
    assert state == "open"
    # subscriptions have no date: not forecast once any statement covers the month (review #7)
    assert refs(items) == ["rec_acc", "tx_imp", "tx_manual_uncovered"]
    rec_item = next(i for i in items if i.ref_id == "rec_acc")
    assert rec_item.purchase_date == date(2026, 9, 29)
    assert rec_item.payment_method is PaymentMethod.PIX


def test_r8_5_account_without_statements_is_projected() -> None:
    txs = [acc_tx("tx_manual", 50, date(2026, 9, 12), manual=True)]
    ledger = mk.ledger(TODAY, accounts=[ACC], transactions=txs)
    state, items = ledger.account_month("acc_x", "2026-09")
    assert (state, refs(items)) == ("projected", ["tx_manual"])


def test_r5_5_pending_statement_counts_only_with_pending_filter() -> None:
    stmt = mk.statement("sha_st", "acc_x", date(2026, 9, 1), date(2026, 9, 30),
                        status="pending_review")  # fmt: skip
    txs = [acc_tx("tx_manual", 50, date(2026, 9, 12), manual=True)]
    staged = [
        acc_tx("stg_1", 70, date(2026, 9, 12), sha="sha_st"),
        acc_tx("stg_overlap", 70, date(2026, 9, 12), sha="sha_st", review_status="overlap"),
    ]
    world = {"accounts": [ACC], "transactions": txs, "staging": staged, "documents": [stmt]}
    confirmed_only = mk.ledger(TODAY, **world)
    state, items = confirmed_only.account_month("acc_x", "2026-09")
    assert (state, refs(items)) == ("open", ["tx_manual"])
    with_pending = mk.ledger(TODAY, include_pending=True, **world)
    state, items = with_pending.account_month("acc_x", "2026-09")
    assert (state, refs(items)) == ("real", ["stg_1"])


def test_r10_4_cash_always_counts() -> None:
    # docs/07: cash transactions are definitive and always count
    wallet = mk.account("acc_cash", type="cash")
    tx = mk.tx("tx_cash", 12, month="2026-09", day=date(2026, 9, 3), account="acc_cash",
               method=PaymentMethod.CASH, manual=True)  # fmt: skip
    assert tx.provisional is False
    forced = tx.model_copy(update={"id": "tx_cash_flagged", "provisional": True})
    stmt = mk.statement("sha_c", "acc_cash", date(2026, 9, 1), date(2026, 9, 30))
    ledger = mk.ledger(TODAY, accounts=[wallet], transactions=[tx, forced], documents=[stmt])
    assert refs(ledger.account_month("acc_cash", "2026-09")[1]) == ["tx_cash", "tx_cash_flagged"]


def test_r11_2_benefit_manuals_count_unless_a_statement_covers_the_day() -> None:
    # docs/16: on a benefit account without statements manuals always count (they are the only
    # record); once a statement covers the day, the statement is the truth (no double count).
    vr = mk.account("acc_vr", type="benefit", confirm_after=45)
    stmt = mk.statement("sha_vr", "acc_vr", date(2026, 8, 1), date(2026, 8, 31))
    old = mk.tx("tx_old", 30, month="2026-08", day=date(2026, 8, 20), account="acc_vr",
                method=PaymentMethod.BENEFIT, manual=True)  # fmt: skip
    recent = mk.tx("tx_recent", 30, month="2026-08", day=date(2026, 8, 31), account="acc_vr",
                   method=PaymentMethod.BENEFIT, manual=True)  # fmt: skip
    covered = mk.ledger(TODAY, accounts=[vr], transactions=[old, recent], documents=[stmt])
    assert covered.account_month("acc_vr", "2026-08")[1] == []
    uncovered = mk.ledger(TODAY, accounts=[vr], transactions=[old, recent])
    assert refs(uncovered.account_month("acc_vr", "2026-08")[1]) == ["tx_old", "tx_recent"]


def test_account_ignores_card_transactions_and_other_months() -> None:
    txs = [
        acc_tx("tx_sep", 10, date(2026, 9, 3), manual=True),
        acc_tx("tx_oct", 10, date(2026, 10, 3), manual=True),
        mk.tx("tx_card", 10, month="2026-09", day=date(2026, 9, 1), card="card_x",
              account="acc_x", manual=True),
    ]  # fmt: skip
    ledger = mk.ledger(TODAY, cards=[CARD], accounts=[ACC], transactions=txs)
    assert refs(ledger.account_month("acc_x", "2026-09")[1]) == ["tx_sep"]


# ---------------------------------------------------------------- month views and helpers


def test_month_view_combines_cards_and_accounts() -> None:
    txs = [
        mk.tx("tx_card", 10, month="2026-12", day=date(2026, 11, 20), card="card_x", manual=True),
        acc_tx("tx_acc", 5, date(2026, 12, 1), manual=True),
    ]
    ledger = mk.ledger(TODAY, cards=[CARD], accounts=[ACC], transactions=txs)
    views = ledger.months(["2026-09", "2026-12"])
    assert [v.month for v in views] == ["2026-09", "2026-12"]
    assert views[0].states == {"card_x": "missing", "acc_x": "projected"}
    assert views[1].states == {"card_x": "projected", "acc_x": "projected"}
    assert refs(views[1].items) == ["tx_acc", "tx_card"]


def test_shares_of_resolves_split_and_falls_back_to_owners_for_unknown_split() -> None:
    casal = mk.split("split_casal", [("2026-01", [(EU, 60), (ANA, 40)])])
    txs = [
        mk.tx("tx_split", 100, month="2026-12", day=date(2026, 11, 20), card="card_x",
              manual=True, allocations=mk.ref("split_casal")),
        mk.tx("tx_ghost", 100, month="2026-12", day=date(2026, 11, 20), card="card_x",
              manual=True, allocations=mk.ref("split_ghost")),
    ]  # fmt: skip
    ledger = mk.ledger(TODAY, cards=[CARD], splits=[casal], transactions=txs)
    items = {i.ref_id: i for i in ledger.card_month("card_x", "2026-12")[1]}
    assert ledger.parts_of(items["tx_split"]) == {EU: D("60.00"), ANA: D("40.00")}
    assert ledger.parts_of(items["tx_ghost"]) == {EU: D("100.00")}


@pytest.mark.parametrize(
    ("today", "first", "last"),
    [(date(2026, 10, 12), "2026-10", "2027-09"), (date(2026, 12, 31), "2026-12", "2027-11"),
     (date(2027, 1, 1), "2027-01", "2027-12")],
)  # fmt: skip
def test_r1_13_projection_is_always_12_months_from_current_month(
    today: date, first: str, last: str
) -> None:
    months = projection_months(today)
    assert len(months) == 12
    assert (months[0], months[-1]) == (first, last)


def test_r1_13_window_fixture_matches_clock(window: list[str]) -> None:
    assert window[0] == "2026-10"


def _item(kind: Kind, amount: str) -> LedgerItem:
    return LedgerItem(
        month="2026-10", description="x", amount=D(amount), kind=kind,
        payment_method=PaymentMethod.CREDIT, origin="transaction", card_id="card_x",
        account_id=None, category_id=None, allocations=None, responsible_user_id=EU,
        owners=mk.shares((EU, 100)), ref_id="x",
    )  # fmt: skip


def test_spending_total_counts_only_spending_kinds() -> None:
    # docs/04 kind table: expense/fee/refund count; income/transfer/settlement/investment don't
    items = [
        _item(Kind.EXPENSE, "100"),
        _item(Kind.FEE, "5"),
        _item(Kind.REFUND, "-20"),
        _item(Kind.INCOME, "1000"),
        _item(Kind.TRANSFER, "300"),
        _item(Kind.SETTLEMENT, "40"),
        _item(Kind.INVESTMENT, "500"),
    ]
    assert spending_total(items) == D("85.00")
    assert not _item(Kind.EXPENSE, "1").is_forecast


def test_document_info_active() -> None:
    assert DocumentInfo("s", "fatura", "confirmed").active
    assert not DocumentInfo("s", "fatura", "error").active


def test_ledger_ignores_documents_without_owner() -> None:
    docs = [DocumentInfo("s1", "fatura", "confirmed"), DocumentInfo("s2", "extrato", "confirmed")]
    ledger = Ledger(mk.state(cards=[CARD], documents=docs), TODAY)
    assert ledger.document_for("card_x", "2026-10") is None
