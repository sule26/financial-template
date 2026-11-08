"""Aggregations: summary, committed income, balances, R6.13 impact, goals (docs/07, 08)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from builders import ANA, EU, PAIS, Builders
from hypothesis import given
from hypothesis import strategies as st

from expense_tracker.domain.ledger import Ledger
from expense_tracker.domain.models import Kind, PaymentMethod, Settlement, Transaction
from expense_tracker.domain.reports import (
    UNCATEGORIZED,
    BalanceLine,
    Balances,
    balances,
    band,
    committed_income,
    goals_progress,
    settlement_impact,
    summarize,
)

D = Decimal
mk = Builders
TODAY = date(2026, 10, 12)
SEP = date(2026, 9, 1)

CARD_CONJ = mk.card("card_conj", owners=mk.shares((EU, 50), (ANA, 50)), responsible=EU)
CARD_EU = mk.card("card_eu", owners=mk.shares((EU, 100)), responsible=EU)
CARD_ANA = mk.card("card_ana", owners=mk.shares((ANA, 100)), responsible=ANA)
CARDS = [CARD_CONJ, CARD_EU, CARD_ANA]
DOCS = [mk.invoice(f"sha_{c.id}", "2026-09", card=c.id) for c in CARDS]


def real_tx(tid: str, amount: str | int, card: str, alloc: list, **kw: object) -> Transaction:  # type: ignore[type-arg]
    return mk.tx(tid, amount, month="2026-09", day=date(2026, 8, 20), card=card,
                 sha=f"sha_{card}", allocations=alloc, **kw)  # type: ignore[arg-type]  # fmt: skip


SALDOS_TXS = [
    real_tx("tx_mercado", 200, "card_conj", mk.shares((EU, 50), (ANA, 50)), category="cat_mercado"),
    real_tx("tx_remedio", 80, "card_eu", mk.shares((PAIS, 100)), category="cat_saude"),
    real_tx("tx_jantar", 120, "card_ana", mk.shares((EU, 50), (ANA, 50)), category="cat_lazer"),
]
ACERTO = mk.settlement(ANA, EU, 40, "2026-09")


def ledger_with(txs: list[Transaction], **kw: object) -> Ledger:
    return mk.ledger(TODAY, cards=CARDS, documents=DOCS, transactions=txs, **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------- balances (docs/08 "Saldos")


def test_r6_3_balances_example_table() -> None:
    # docs/08#saldos: Mercado 200 (Ana owes me 100), Remédio 80 (parents owe me 80),
    # Jantar 120 (I owe Ana 60), settlement Ana paid me 40 -> me x Ana = 0
    ledger = ledger_with(SALDOS_TXS)
    result = balances(ledger, ledger.months(["2026-09"]), [ACERTO])
    lines = {(ln.ref_id, ln.creditor, ln.debtor): ln.amount for ln in result.lines}
    assert lines == {
        ("tx_mercado", EU, ANA): D("100.00"),
        ("tx_remedio", EU, PAIS): D("80.00"),
        ("tx_jantar", ANA, EU): D("60.00"),
    }
    assert result.net(EU, ANA) == D("0.00")
    assert result.net(EU, PAIS) == D("80.00")
    assert result.net(PAIS, EU) == D("-80.00")
    assert result.counterparties(EU) == [ANA, PAIS]
    assert result.counterparties(PAIS) == [EU]
    assert result.incomplete_months == set()


def test_r6_4_balance_without_settlement() -> None:
    ledger = ledger_with(SALDOS_TXS)
    result = balances(ledger, ledger.months(["2026-09"]), [])
    assert result.net(EU, ANA) == D("40.00")  # 100 - 60: Ana owes me 40
    assert result.net(ANA, EU) == D("-40.00")


def test_r6_4_settlement_from_a_to_b_increases_net_of_a() -> None:
    ledger = ledger_with([])
    result = balances(ledger, ledger.months(["2026-09"]), [mk.settlement(EU, ANA, 25, "2026-09")])
    assert result.net(EU, ANA) == D("25.00")
    assert result.counterparties(ANA) == [EU]


def test_r6_3_refund_reduces_debt() -> None:
    refund = real_tx("tx_estorno", -50, "card_conj", mk.shares((EU, 50), (ANA, 50)),
                     kind=Kind.REFUND)  # fmt: skip
    ledger = ledger_with([*SALDOS_TXS, refund])
    result = balances(ledger, ledger.months(["2026-09"]), [ACERTO])
    assert result.net(EU, ANA) == D("-25.00")


def test_r6_5_balances_by_month_and_non_spending_kinds_are_ignored() -> None:
    transfer = real_tx("tx_transf", 999, "card_conj", mk.shares((ANA, 100)), kind=Kind.INVESTMENT)
    ledger = ledger_with([*SALDOS_TXS, transfer])
    result = balances(ledger, ledger.months(["2026-09"]), [ACERTO])
    assert result.net(EU, ANA, "2026-09") == D("0.00")
    assert result.net(EU, ANA, "2026-08") == D("0.00")
    assert all(ln.ref_id != "tx_transf" for ln in result.lines)


def test_r6_3_forecasts_are_not_debts_but_provisional_manuals_are() -> None:
    plan = mk.plan("plan_x", n=1, total=100, first="2026-12", card="card_conj")
    manual = mk.tx("tx_manual", 30, month="2026-12", day=date(2026, 11, 20), card="card_conj",
                   manual=True)  # fmt: skip
    ledger = mk.ledger(TODAY, cards=CARDS, plans=[plan], transactions=[manual])
    result = balances(ledger, ledger.months(["2026-12"]), [])
    assert [(ln.ref_id, ln.debtor, ln.amount) for ln in result.lines] == [
        ("tx_manual", ANA, D("15.00"))
    ]


def test_r8_9_missing_month_marks_balances_incomplete() -> None:
    ledger = mk.ledger(TODAY, cards=CARDS, transactions=[])
    result = balances(ledger, ledger.months(["2026-09", "2026-12"]), [])
    assert result.incomplete_months == {"2026-09"}


def test_r6_13_settlement_impact_reports_changed_settled_months() -> None:
    # docs/08#mudanças-que-afetam-meses-já-acertados-r613
    ledger = ledger_with(SALDOS_TXS)
    before = balances(ledger, ledger.months(["2026-09"]), [ACERTO])
    changed = [
        real_tx("tx_mercado", 200, "card_conj", mk.shares((EU, 60), (ANA, 40))),
        *SALDOS_TXS[1:],
    ]
    after_ledger = ledger_with(changed)
    after = balances(after_ledger, after_ledger.months(["2026-09"]), [ACERTO])
    impact = settlement_impact(before, after, ["2026-09"])
    # Ana now owes 80 instead of 100: me x Ana goes from 0,00 to -20,00 (Ana x me: 0 -> 20)
    assert impact == [("2026-09", ANA, EU, D("0.00"), D("20.00"))]
    assert settlement_impact(before, after, ["2026-08"]) == []
    assert settlement_impact(before, before, ["2026-09"]) == []


# ---------------------------------------------------------------- summary (docs/07 "Resumo")


def summary_ledger() -> Ledger:
    acc = mk.account("acc_x", owners=mk.shares((EU, 100)))
    vr = mk.account("acc_vr", type="benefit")
    wallet = mk.account("acc_cash", type="cash")
    txs = [
        *SALDOS_TXS,
        real_tx("tx_nocat", 10, "card_eu", mk.shares((EU, 100))),
        real_tx("tx_inc", 5000, "card_eu", mk.shares((EU, 100)), kind=Kind.INCOME),
        mk.tx("tx_pix", 70, month="2026-09", day=SEP, account="acc_x", method=PaymentMethod.PIX,
              manual=True, category="cat_mercado"),
        mk.tx("tx_vr", 40, month="2026-09", day=SEP, account="acc_vr",
              method=PaymentMethod.BENEFIT, manual=True, category="cat_mercado"),
        mk.tx("tx_cash", 12, month="2026-09", day=SEP, account="acc_cash",
              method=PaymentMethod.CASH, manual=True, category="cat_lazer"),
    ]  # fmt: skip
    users = [
        mk.user(EU, income=[("2026-01", "9000")], benefit=[("2026-01", "800")]),
        mk.user(ANA),
        mk.user(PAIS),
    ]
    return mk.ledger(TODAY, cards=CARDS, accounts=[acc, vr, wallet], documents=DOCS,
                     transactions=txs, users=users)  # fmt: skip


def test_r1_6_summarize_by_category_card_and_method_full_amount() -> None:
    ledger = summary_ledger()
    view = ledger.month("2026-09")
    s = summarize(ledger, view)
    assert s.total == D("532.00")  # 200 + 80 + 120 + 10 + 70 + 40 + 12 (income excluded)
    assert s.by_category == {
        "cat_mercado": D("310.00"),
        "cat_saude": D("80.00"),
        "cat_lazer": D("132.00"),
        UNCATEGORIZED: D("10.00"),  # R1.12 "Sem categoria"
    }
    assert s.by_card == {
        "card_conj": D("200.00"),
        "card_eu": D("90.00"),
        "card_ana": D("120.00"),
        "acc_x": D("70.00"),
        "acc_vr": D("40.00"),
        "acc_cash": D("12.00"),
    }
    assert s.by_method == {
        "credit": D("410.00"),
        "account": D("70.00"),
        "benefit": D("40.00"),
        "cash": D("12.00"),
    }
    # R14.6 (changed from None): without a person, the household income (only EU has income here).
    assert (s.income, s.benefit_income) == (D("9000.00"), D("800.00"))
    assert s.states["card_conj"] == "real"


def test_r11_4_summarize_filtered_by_payment_method() -> None:
    ledger = summary_ledger()
    s = summarize(ledger, ledger.month("2026-09"), method_group="benefit")
    assert (s.total, s.by_method) == (D("40.00"), {"benefit": D("40.00")})


def test_r1_6_summarize_for_user_counts_only_their_part() -> None:
    ledger = summary_ledger()
    users = ledger.s.users
    s = summarize(ledger, ledger.month("2026-09"), user=users[EU])
    # 100 (mercado) + 60 (jantar) + 10 + 70 + 40 + 12; remédio is the parents'
    assert s.total == D("292.00")
    assert "cat_saude" not in s.by_category
    assert (s.income, s.benefit_income) == (D("9000.00"), D("800.00"))
    pais = summarize(ledger, ledger.month("2026-09"), user=users[PAIS])
    assert (pais.total, pais.by_category) == (D("80.00"), {"cat_saude": D("80.00")})


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(None, None), (D("49.99"), "green"), (D("50.00"), "yellow"), (D("80.00"), "yellow"),
     (D("80.01"), "red")],
)  # fmt: skip
def test_r1_9_committed_income_bands(ratio: Decimal | None, expected: str | None) -> None:
    # docs/07#resumo: < 50% green, 50–80% yellow, > 80% red
    assert band(ratio) == expected


def test_r1_9_committed_income_bands_are_configurable() -> None:
    assert band(D("40"), warn=D(30), alert=D(60)) == "yellow"
    assert band(D("61"), warn=D(30), alert=D(60)) == "red"


def test_r1_9_committed_income_cash_and_benefit_separately() -> None:
    ledger = summary_ledger()
    eu = ledger.s.users[EU]
    (c,) = committed_income(ledger, [ledger.month("2026-09")], eu)
    assert (c.month, c.spent, c.income, c.ratio, c.band) == (
        "2026-09", D("252.00"), D("9000.00"), D("2.80"), "green",
    )  # fmt: skip
    assert (c.benefit_spent, c.benefit_income, c.benefit_ratio) == (
        D("40.00"), D("800.00"), D("5.00"),
    )  # fmt: skip


def test_r1_9_committed_income_not_shown_without_income() -> None:
    ledger = summary_ledger()
    (c,) = committed_income(ledger, [ledger.month("2026-09")], ledger.s.users[ANA])
    assert c.spent == D("160.00")  # 100 (mercado) + 60 (jantar)
    assert (c.income, c.ratio, c.band, c.benefit_ratio) == (None, None, None, None)


def test_r1_9_committed_income_uses_projection_for_future_months() -> None:
    plan = mk.plan("plan_x", n=1, total=4500, first="2026-12", card="card_eu")
    users = [mk.user(EU, income=[("2026-01", "5000")])]
    ledger = mk.ledger(TODAY, cards=CARDS, plans=[plan], users=users)
    (c,) = committed_income(ledger, [ledger.month("2026-12")], users[0])
    assert (c.spent, c.ratio, c.band) == (D("4500.00"), D("90.00"), "red")


def test_r9_6_goals_progress() -> None:
    from expense_tracker.domain.models import SavingsGoal

    goals = [
        SavingsGoal(id="goal_reserva", name="Reserva", monthly_amount=D("1000")),
        SavingsGoal(id="goal_viagem", name="Viagem", monthly_amount=D("300")),
    ]
    assert goals_progress(goals, {"goal_reserva": D("800.00")}) == {
        "goal_reserva": (D("1000.00"), D("800.00")),
        "goal_viagem": (D("300.00"), D("0.00")),
    }


# ---------------------------------------------------------------- property


PEOPLE = st.sampled_from([EU, ANA, PAIS])
AMOUNTS = st.integers(min_value=1, max_value=1_000_000).map(lambda c: D(c) / 100)


@st.composite
def balance_lines(draw: st.DrawFn) -> BalanceLine:
    creditor = draw(PEOPLE)
    debtor = draw(PEOPLE.filter(lambda p: p != creditor))
    month = draw(st.sampled_from(["2026-09", "2026-10"]))
    return BalanceLine(month, "tx", "x", creditor, debtor, draw(AMOUNTS))


@st.composite
def settlements(draw: st.DrawFn) -> Settlement:
    frm = draw(PEOPLE)
    to = draw(PEOPLE.filter(lambda p: p != frm))
    return mk.settlement(frm, to, draw(AMOUNTS), draw(st.sampled_from(["2026-09", "2026-10"])))


@given(
    lines=st.lists(balance_lines(), max_size=20),
    sets=st.lists(settlements(), max_size=10),
    a=PEOPLE,
    b=PEOPLE,
    month=st.sampled_from([None, "2026-09", "2026-10"]),
)
def test_r6_5_balance_is_antisymmetric(
    lines: list[BalanceLine], sets: list[Settlement], a: str, b: str, month: str | None
) -> None:
    result = Balances(lines=lines, settlements=sets)
    assert result.net(a, b, month) == -result.net(b, a, month)
