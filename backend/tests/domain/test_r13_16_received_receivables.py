"""R13.16: settlements linked to a receivable (card/account + invoice month) mark it received."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from builders import ANA, EU, PAIS, Builders
from pydantic import ValidationError

from expense_tracker.domain.models import Settlement
from expense_tracker.domain.reports import BalanceLine, Balances, linked_settled, receivables

D = Decimal
mk = Builders
DUE = date(2026, 10, 10)
LATE = date(2026, 10, 12)


def _set(sid: str, frm: str, to: str, amount: int, **link: Any) -> Settlement:
    return Settlement(id=sid, from_user_id=frm, to_user_id=to, amount=D(amount),
                      date=date(2026, 10, 11), month="2026-10", **link)  # fmt: skip


def _line(cred: str, debt: str, amount: int, card: str | None = "card_x", acc: str | None = None,
          month: str = "2026-10") -> BalanceLine:  # fmt: skip
    due = DUE if card else None
    return BalanceLine(month, "r", "R", cred, debt, D(amount), card, acc, due)


LINK = {"card_id": "card_x", "invoice_month": "2026-10"}


def _rows(sets: list[Settlement], user: str = EU) -> list[tuple[Any, ...]]:
    lines = [_line(EU, ANA, 100), _line(EU, ANA, 40, card=None, acc="acc_x")]
    bal = Balances(lines=lines, settlements=sets)
    return [
        (r.card_id, r.account_id, r.amount, r.settled, r.remaining, r.status, r.overdue)
        for r in receivables(bal, user, LATE)
    ]


def test_r13_16_open_when_nothing_linked() -> None:
    unlinked = _set("s0", ANA, EU, 100)  # net balance only (legacy / no card)
    assert _rows([unlinked]) == [
        ("card_x", None, D(100), D(0), D(100), "open", True),
        (None, "acc_x", D(40), D(0), D(40), "open", False),
    ]


def test_r13_16_partial_then_received_and_overdue_only_while_remaining() -> None:
    part = _set("s1", ANA, EU, 30, **LINK)
    assert _rows([part])[0] == ("card_x", None, D(100), D(30), D(70), "partial", True)
    rest = _set("s2", ANA, EU, 70, **LINK)
    assert _rows([part, rest])[0] == ("card_x", None, D(100), D(100), D(0), "received", False)
    over = _set("s3", ANA, EU, 150, **LINK)  # overpaid: remaining never goes below zero
    assert _rows([over])[0] == ("card_x", None, D(100), D(150), D(0), "received", False)


def test_r13_16_only_same_pair_direction_card_and_month_count() -> None:
    noise = [
        _set("a", EU, ANA, 50, **LINK),  # opposite direction
        _set("b", PAIS, EU, 50, **LINK),  # other counterparty
        _set("c", ANA, EU, 50, card_id="card_y", invoice_month="2026-10"),  # other card
        _set("d", ANA, EU, 50, card_id="card_x", invoice_month="2026-09"),  # other month
        _set("e", ANA, EU, 50, account_id="acc_x", invoice_month="2026-09"),
    ]
    assert [row[3] for row in _rows(noise)] == [D(0), D(0)]
    acc = _set("f", ANA, EU, 40, account_id="acc_x", invoice_month="2026-10")
    assert _rows([acc])[1] == (None, "acc_x", D(40), D(40), D(0), "received", False)


def test_r13_16_pay_direction_counts_what_the_user_paid() -> None:
    paid = _set("s1", ANA, EU, 100, **LINK)
    rows = receivables(Balances(lines=[_line(EU, ANA, 100)], settlements=[paid]), ANA, LATE)
    assert [(r.direction, r.settled, r.remaining, r.status) for r in rows] == [
        ("pay", D(100), D(0), "received")
    ]


def test_r13_16_linked_settled_helper() -> None:
    sets = [_set("s1", ANA, EU, 10, **LINK), _set("s2", ANA, EU, 5)]
    assert linked_settled(sets, ANA, EU, "card_x", None, "2026-10") == D(10)
    assert linked_settled(sets, EU, ANA, "card_x", None, "2026-10") == D(0)


def test_r13_16_settlement_link_validation() -> None:
    assert _set("s1", ANA, EU, 10, **LINK).linked
    assert not _set("s2", ANA, EU, 10).linked
    with pytest.raises(ValidationError, match="not both"):
        _set("s3", ANA, EU, 10, card_id="c", account_id="a", invoice_month="2026-10")
    with pytest.raises(ValidationError, match="needs invoice_month"):
        _set("s4", ANA, EU, 10, card_id="c")
    with pytest.raises(ValidationError, match="needs invoice_month"):
        _set("s5", ANA, EU, 10, account_id="a")
