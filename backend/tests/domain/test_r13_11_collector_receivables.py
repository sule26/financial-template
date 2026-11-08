"""R13.11: "repassar para" (collector) in balances and receivables by card/account and due date."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from builders import ANA, EU, PAIS, Builders

from expense_tracker.domain.ledger import Ledger
from expense_tracker.domain.models import PaymentMethod, Transaction, User
from expense_tracker.domain.reports import (
    BalanceLine,
    Balances,
    balances,
    creditor_for,
    invoice_due_date,
    receivables,
)

D = Decimal
mk = Builders
TODAY = date(2026, 10, 12)
AUG = date(2026, 8, 20)

CARD_EU = mk.card("card_eu", owners=mk.shares((EU, 100)), responsible=EU)  # closing 3 / due 10
CARD_EU_ADD = mk.card("card_eu_add", parent="card_eu", responsible=None)
CARD_EU2 = mk.card("card_eu2", 20, 28, owners=mk.shares((EU, 100)), responsible=EU)
CARD_ANA = mk.card("card_ana", owners=mk.shares((ANA, 100)), responsible=ANA)
ACC = mk.account("acc_conj", owners=mk.shares((EU, 50), (ANA, 50)), responsible=EU)
HALF = mk.shares((EU, 50), (ANA, 50))

DOCS = [
    replace(mk.invoice("sha_card_eu", "2026-09", card="card_eu"), due_date=date(2026, 10, 20)),
    mk.invoice("sha_card_eu2", "2026-09", card="card_eu2"),
    mk.invoice("sha_card_ana", "2026-09", card="card_ana"),
    mk.statement("sha_acc", "acc_conj", date(2026, 9, 1), date(2026, 9, 30)),
]


def card_tx(
    tid: str, amount: int, card: str, alloc: list, sha_card: str | None = None
) -> Transaction:  # type: ignore[type-arg]
    return mk.tx(tid, amount, month="2026-09", day=AUG, card=card,
                 sha=f"sha_{sha_card or card}", allocations=alloc)  # fmt: skip


TXS = [
    card_tx("tx_remedio", 100, "card_eu", mk.shares((PAIS, 100))),  # Pais -> Ana (collector)
    card_tx("tx_mercado", 50, "card_eu", HALF),  # Ana owes me 25
    card_tx("tx_add", 20, "card_eu_add", mk.shares((ANA, 100)), "card_eu"),  # additional card
    card_tx("tx_posto", 80, "card_eu2", HALF),  # Ana owes me 40 on another card
    card_tx("tx_jantar", 60, "card_ana", HALF),  # I owe Ana 30
    mk.tx(
        "tx_luz",
        40,
        month="2026-09",
        day=date(2026, 9, 5),
        account="acc_conj",
        method=PaymentMethod.DEBIT,
        sha="sha_acc",
        allocations=HALF,
    ),  # fmt: skip
]

USERS = [
    mk.user(EU, "Eu"),
    mk.user(ANA, "Ana"),
    User(id=PAIS, name="Pais", collector_user_id=ANA),
]


def ledger() -> Ledger:
    return mk.ledger(
        TODAY,
        users=USERS,
        cards=[CARD_EU, CARD_EU_ADD, CARD_EU2, CARD_ANA],
        accounts=[ACC],
        documents=DOCS,
        transactions=TXS,
    )


def test_r13_11_debts_go_to_the_collector_and_lines_carry_card_and_due_date() -> None:
    led = ledger()
    bal = balances(led, led.months(["2026-09"]), [])
    remedios = [ln for ln in bal.lines if ln.ref_id == "tx_remedio"]
    assert [(ln.creditor, ln.debtor, ln.amount) for ln in remedios] == [
        (ANA, PAIS, D(100)),
        (EU, ANA, D(100)),  # R13.14: Ana passes it on to me (the responsible)
    ]
    remedio = remedios[0]
    by_ref = {ln.ref_id: ln for ln in bal.lines}
    assert remedio.card_id == "card_eu"
    assert remedio.account_id is None
    assert remedio.due_date == date(2026, 10, 20)  # active document's due date wins
    add = by_ref["tx_add"]
    assert add.card_id == "card_eu"  # additional card bills on the main card
    assert by_ref["tx_posto"].due_date == date(2026, 9, 28)  # planned from billing history
    luz = by_ref["tx_luz"]
    assert (luz.card_id, luz.account_id, luz.due_date) == (None, "acc_conj", None)
    # parents owe Ana (collector), not me; Ana owes it on to me (R13.14)
    assert bal.net(ANA, PAIS) == D(100)
    assert bal.net(EU, PAIS) == D(0)


def test_r13_11_creditor_for_falls_back_to_responsible() -> None:
    users = {u.id: u for u in USERS}
    assert creditor_for(PAIS, EU, users) == ANA
    assert creditor_for(ANA, EU, users) == EU  # no collector
    assert creditor_for("usr_ghost", EU, users) == EU  # unknown user
    selfish = {PAIS: User(id=PAIS, name="Pais", collector_user_id=PAIS)}
    assert creditor_for(PAIS, EU, selfish) == EU  # self-collector is ignored


def test_r13_11_collector_who_is_responsible_has_no_double_debt() -> None:
    # Pais buy on Ana's card (Ana responsible, also Pais' collector): one debt Pais -> Ana.
    txs = [card_tx("tx_x", 30, "card_ana", mk.shares((PAIS, 100)))]
    led = mk.ledger(TODAY, users=USERS, cards=[CARD_ANA], documents=DOCS, transactions=txs)
    bal = balances(led, led.months(["2026-09"]), [])
    assert [(ln.creditor, ln.debtor, ln.amount) for ln in bal.lines] == [(ANA, PAIS, D(30))]


def test_r13_11_receivables_one_per_card_and_month_sorted_by_due_date() -> None:
    led = ledger()
    settle = mk.settlement(ANA, EU, 30, "2026-09")
    bal = balances(led, led.months(["2026-09"]), [settle])
    rows = receivables(bal, EU, TODAY)
    got = [
        (r.counterparty_user_id, r.direction, r.card_id, r.account_id, r.due_date, r.amount)
        for r in rows
    ]
    assert got == [
        (ANA, "pay", "card_ana", None, date(2026, 9, 10), D(30)),
        (ANA, "receive", "card_eu2", None, date(2026, 9, 28), D(40)),
        # 25 + 20 (additional) + 100 passed on by Ana (R13.14)
        (ANA, "receive", "card_eu", None, date(2026, 10, 20), D(145)),
        (ANA, "receive", None, "acc_conj", None, D(20)),  # accounts (no due date) last
    ]
    assert [r.overdue for r in rows] == [True, True, False, False]
    assert {r.invoice_month for r in rows} == {"2026-09"}
    assert {r.settled_month_total for r in rows} == {D(30)}  # Ana paid me 30 that month

    ana = receivables(bal, ANA, TODAY)
    pais = [r for r in ana if r.counterparty_user_id == PAIS]
    assert [(r.direction, r.card_id, r.amount) for r in pais] == [("receive", "card_eu", D(100))]
    assert pais[0].settled_month_total == D(0)
    to_eu = [r for r in ana if r.counterparty_user_id == EU]
    assert {r.settled_month_total for r in to_eu} == {D(-30)}  # Ana paid me


def test_r13_11_receivables_net_within_group_and_skip_others() -> None:
    lines = [
        BalanceLine("2026-09", "a", "A", EU, ANA, D(10), "card_x", None, date(2026, 9, 10)),
        BalanceLine("2026-09", "b", "B", ANA, EU, D(10), "card_x", None, date(2026, 9, 10)),
        BalanceLine("2026-09", "c", "C", ANA, PAIS, D(5), "card_x", None, date(2026, 9, 10)),
        BalanceLine("2026-10", "d", "D", ANA, EU, D(7), "card_x", None, date(2026, 10, 10)),
    ]
    sets = [mk.settlement(EU, ANA, 3, "2026-10"), mk.settlement(EU, ANA, 1, "2026-11", "s2")]
    rows = receivables(Balances(lines=lines, settlements=sets), EU, date(2026, 10, 10))
    # Sept nets to zero (skipped); Pais line does not involve me; Oct: I pay 7
    assert [(r.invoice_month, r.direction, r.amount, r.overdue) for r in rows] == [
        ("2026-10", "pay", D(7), False)  # due today is not overdue
    ]
    assert rows[0].settled_month_total == D(-3)


def test_r13_11_invoice_due_date_unknown_card() -> None:
    assert invoice_due_date(ledger(), "card_ghost", "2026-09") is None
