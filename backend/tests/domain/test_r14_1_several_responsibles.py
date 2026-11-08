"""R14.1: a card/account may have several responsibles (who pay the bank) with percentages.

Each person's part is owed to each responsible in proportion; the share a responsible pays
for themselves is not a debt. One responsible keeps the R6.8 behaviour.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from builders import ANA, EU, PAIS, Builders
from pydantic import ValidationError

from expense_tracker.domain.allocation import resolve_account, resolve_card
from expense_tracker.domain.models import Account, Card, SplitRef
from expense_tracker.domain.reports import balances

D = Decimal
mk = Builders
TODAY = date(2026, 10, 12)


def _card(cid: str, owners: list, responsible: str, responsibles: object) -> Card:  # type: ignore[type-arg]
    return mk.card(cid, owners=owners, responsible=responsible).model_copy(
        update={"responsibles": responsibles}
    )


def _ledger(card: Card, *txs: object, **kw: object) -> object:
    doc = mk.invoice(f"sha_{card.id}", "2026-09", card=card.id)
    return mk.ledger(TODAY, cards=[card], documents=[doc], transactions=list(txs), **kw)  # type: ignore[arg-type]


def _tx(tid: str, amount: int | str, card: str, alloc: list) -> object:  # type: ignore[type-arg]
    return mk.tx(tid, amount, month="2026-09", day=date(2026, 8, 20), card=card,
                 sha=f"sha_{card}", allocations=alloc)  # fmt: skip


def _lines(ledger: object) -> set[tuple[str, str, Decimal]]:
    bal = balances(ledger, [ledger.month("2026-09")], [])  # type: ignore[attr-defined, arg-type]
    return {(ln.creditor, ln.debtor, ln.amount) for ln in bal.lines}


def test_r14_1_part_owed_to_each_responsible_in_proportion() -> None:
    # Eu and Ana pay the bank 60/40; Pais bought 100 for themselves.
    card = _card("card_c", mk.shares((EU, 50), (ANA, 50)), EU, mk.shares((EU, 60), (ANA, 40)))
    ledger = _ledger(card, _tx("tx_1", 100, "card_c", mk.shares((PAIS, 100))))
    assert _lines(ledger) == {(EU, PAIS, D("60.00")), (ANA, PAIS, D("40.00"))}


def test_r14_1_a_responsible_does_not_owe_their_own_paid_share() -> None:
    # Shared 50/50 purchase paid 60/40: Ana owes Eu 30 (her 50 × Eu's 60%),
    # Eu owes Ana 20 (his 50 × Ana's 40%) — net Ana owes 10, as she paid 40 and consumed 50.
    card = _card("card_c", mk.shares((EU, 50), (ANA, 50)), EU, mk.shares((EU, 60), (ANA, 40)))
    ledger = _ledger(card, _tx("tx_1", 100, "card_c", mk.shares((EU, 50), (ANA, 50))))
    assert _lines(ledger) == {(EU, ANA, D("30.00")), (ANA, EU, D("20.00"))}
    bal = balances(ledger, [ledger.month("2026-09")], [])  # type: ignore[attr-defined, arg-type]
    assert bal.net(EU, ANA) == D("10.00")


def test_r14_1_cents_residue_goes_to_the_main_responsible() -> None:
    card = _card("card_c", mk.shares((PAIS, 100)), ANA, mk.shares((EU, "33.33"), (ANA, "66.67")))
    ledger = _ledger(card, _tx("tx_1", "0.10", "card_c", mk.shares((PAIS, 100))))
    # 0.10 × 33.33% = 0.0333 → 0.03; 0.10 × 66.67% = 0.0667 → 0.07 (sum exact: 0.10)
    assert _lines(ledger) == {(EU, PAIS, D("0.03")), (ANA, PAIS, D("0.07"))}


def test_r14_1_single_responsible_behaves_as_before() -> None:
    card = mk.card("card_c", owners=mk.shares((EU, 100)), responsible=EU)
    ledger = _ledger(card, _tx("tx_1", 80, "card_c", mk.shares((PAIS, 100))))
    assert _lines(ledger) == {(EU, PAIS, D("80.00"))}


def test_r14_1_responsibles_can_be_a_split_profile() -> None:
    split = mk.split("split_casal", [("2026-01", [(EU, 60), (ANA, 40)])])
    card = _card("card_c", mk.shares((PAIS, 100)), EU, SplitRef(split_id="split_casal"))
    ledger = _ledger(card, _tx("tx_1", 50, "card_c", mk.shares((PAIS, 100))), splits=[split])
    assert _lines(ledger) == {(EU, PAIS, D("30.00")), (ANA, PAIS, D("20.00"))}


def test_r14_1_unknown_split_of_responsibles_falls_back_to_the_main_responsible() -> None:
    card = _card("card_c", mk.shares((PAIS, 100)), EU, SplitRef(split_id="gone"))
    ledger = _ledger(card, _tx("tx_1", 50, "card_c", mk.shares((PAIS, 100))))
    assert _lines(ledger) == {(EU, PAIS, D("50.00"))}


def test_r14_1_collector_applies_to_each_responsible() -> None:
    # Pais pass their debts on to Ana; Eu and Ana pay 50/50: Pais owe Ana all 100
    # (50 for her own payment + 50 she collects for Eu), and Ana owes Eu his 50 (R13.14).
    card = _card("card_c", mk.shares((PAIS, 100)), EU, mk.shares((EU, 50), (ANA, 50)))
    pais = mk.user(PAIS).model_copy(update={"collector_user_id": ANA})
    ledger = _ledger(
        card,
        _tx("tx_1", 100, "card_c", mk.shares((PAIS, 100))),
        users=[mk.user(EU), mk.user(ANA), pais],
    )
    bal = balances(ledger, [ledger.month("2026-09")], [])  # type: ignore[attr-defined, arg-type]
    assert bal.net(ANA, PAIS) == D("100.00")
    assert bal.net(EU, ANA) == D("50.00")
    assert bal.net(EU, PAIS) == D("0.00")


def test_r14_1_card_inherits_responsibles_with_the_main_responsible() -> None:
    acc = mk.account("acc_c", owners=mk.shares((EU, 50), (ANA, 50)), responsible=EU)
    acc = acc.model_copy(update={"responsibles": mk.shares((EU, 70), (ANA, 30))})
    inheriting = mk.card("card_a", responsible=None, account="acc_c")
    own = resolve_card(inheriting, {}, {"acc_c": acc})
    assert (own.responsible_user_id, own.responsibles) == (EU, acc.responsibles)
    # A card with its own single responsible does not mix in the account's responsibles.
    own_card = mk.card("card_b", responsible=ANA, account="acc_c")
    own2 = resolve_card(own_card, {}, {"acc_c": acc})
    assert (own2.responsible_user_id, own2.responsibles) == (ANA, None)
    assert resolve_account(acc).responsibles == acc.responsibles


def test_r14_1_validation() -> None:
    owners = mk.shares((EU, 100))
    with pytest.raises(ValidationError, match="must be one of the responsibles"):
        Account(id="a", name="A", owners=owners, responsible_user_id=PAIS,
                responsibles=mk.shares((EU, 50), (ANA, 50)))  # fmt: skip
    with pytest.raises(ValidationError):
        Account(id="a", name="A", owners=owners, responsible_user_id=EU,
                responsibles=mk.shares((EU, 50), (ANA, 40)))  # fmt: skip
    with pytest.raises(ValidationError, match="needs responsible_user_id"):
        Card(id="c", name="C", parent_card_id="p", responsibles=mk.shares((EU, 100)))
    ok = Card(id="c", name="C", parent_card_id="p", responsible_user_id=EU,
              responsibles=SplitRef(split_id="s"))  # fmt: skip
    assert ok.responsibles == SplitRef(split_id="s")
