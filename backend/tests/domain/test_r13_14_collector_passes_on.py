"""R13.14: a collector who is not the responsible owes the collected amount on to them."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from builders import ANA, EU, PAIS, Builders

from expense_tracker.domain.ledger import Ledger
from expense_tracker.domain.models import PaymentMethod, Transaction, User
from expense_tracker.domain.reports import balances, receivables

D = Decimal
mk = Builders
TODAY = date(2026, 10, 12)

CARD_EU = mk.card("card_eu", owners=mk.shares((EU, 100)), responsible=EU)  # closing 3 / due 10
CARD_ANA = mk.card("card_ana", owners=mk.shares((ANA, 100)), responsible=ANA)
ACC = mk.account("acc_eu", owners=mk.shares((EU, 100)), responsible=EU)
DOCS = [
    mk.invoice("sha_card_eu", "2026-09", card="card_eu"),
    mk.invoice("sha_card_ana", "2026-09", card="card_ana"),
    mk.statement("sha_acc", "acc_eu", date(2026, 9, 1), date(2026, 9, 30)),
]
USERS = [mk.user(EU, "Eu"), mk.user(ANA, "Ana"), User(id=PAIS, name="Pais", collector_user_id=ANA)]


def _tx(tid: str, amount: int, alloc: list, card: str | None = "card_eu") -> Transaction:  # type: ignore[type-arg]
    if card is None:
        return mk.tx(tid, amount, month="2026-09", day=date(2026, 9, 5), account="acc_eu",
                     method=PaymentMethod.DEBIT, sha="sha_acc", allocations=alloc)  # fmt: skip
    return mk.tx(tid, amount, month="2026-09", day=date(2026, 8, 20), card=card,
                 sha=f"sha_{card}", allocations=alloc)  # fmt: skip


def _ledger(*txs: Transaction) -> Ledger:
    return mk.ledger(TODAY, users=USERS, cards=[CARD_EU, CARD_ANA], accounts=[ACC],
                     documents=DOCS, transactions=list(txs))  # fmt: skip


def test_r13_14_collector_line_copies_card_due_date_and_month() -> None:
    led = _ledger(_tx("tx_remedio", 80, mk.shares((PAIS, 100))))
    bal = balances(led, led.months(["2026-09"]), [])
    got = [
        (ln.creditor, ln.debtor, ln.amount, ln.card_id, ln.account_id, ln.due_date, ln.month)
        for ln in bal.lines
    ]
    due = date(2026, 9, 10)
    assert got == [
        (ANA, PAIS, D(80), "card_eu", None, due, "2026-09"),  # Pais -> Ana (collector)
        (EU, ANA, D(80), "card_eu", None, due, "2026-09"),  # Ana -> me (responsible)
    ]
    assert {ln.ref_id for ln in bal.lines} == {"tx_remedio"}
    # nobody's money is lost: I am owed by Ana, Ana is owed by Pais
    assert bal.net(EU, ANA) == D(80)
    assert bal.net(ANA, PAIS) == D(80)
    assert bal.net(EU, PAIS) == D(0)


def test_r13_14_collector_line_on_an_account() -> None:
    led = _ledger(_tx("tx_luz", 40, mk.shares((PAIS, 100)), card=None))
    bal = balances(led, led.months(["2026-09"]), [])
    got = [(ln.creditor, ln.debtor, ln.card_id, ln.account_id, ln.due_date) for ln in bal.lines]
    assert got == [(ANA, PAIS, None, "acc_eu", None), (EU, ANA, None, "acc_eu", None)]


def test_r13_14_collector_is_the_responsible_keeps_only_the_original_line() -> None:
    led = _ledger(_tx("tx_x", 30, mk.shares((PAIS, 100)), card="card_ana"))
    bal = balances(led, led.months(["2026-09"]), [])
    assert [(ln.creditor, ln.debtor, ln.amount) for ln in bal.lines] == [(ANA, PAIS, D(30))]


def test_r13_14_mixed_split_and_receivables() -> None:
    # 100 on my card: Ana 50 (her own part) + Pais 50 (collected by Ana)
    led = _ledger(_tx("tx_mix", 100, mk.shares((ANA, 50), (PAIS, 50))))
    bal = balances(led, led.months(["2026-09"]), [])
    assert sorted((ln.creditor, ln.debtor, ln.amount) for ln in bal.lines) == [
        (ANA, PAIS, D(50)),
        (EU, ANA, D(50)),
        (EU, ANA, D(50)),
    ]
    mine = receivables(bal, EU, TODAY)
    assert [(r.counterparty_user_id, r.direction, r.card_id, r.amount) for r in mine] == [
        (ANA, "receive", "card_eu", D(100))
    ]
    ana = receivables(bal, ANA, TODAY)
    assert sorted((r.counterparty_user_id, r.direction, r.amount) for r in ana) == [
        (EU, "pay", D(100)),
        (PAIS, "receive", D(50)),
    ]
