"""R13.17: a benefit card (VR/VA) is an account of type benefit with a renewal day, no billing."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from expense_tracker.domain.models import Account

OWNERS = [{"user_id": "u1", "pct": "100.00"}]


def _account(**over: Any) -> Account:
    data: dict[str, Any] = {
        "id": "acc_vr",
        "name": "VR",
        "type": "benefit",
        "owners": OWNERS,
        "responsible_user_id": "u1",
        **over,
    }
    return Account.model_validate(data)


def test_r13_17_benefit_account_accepts_renewal_day() -> None:
    assert _account(renewal_day=5).renewal_day == 5


def test_r13_17_renewal_day_is_optional_and_defaults_to_none() -> None:
    assert _account().renewal_day is None
    assert _account(type="checking").renewal_day is None


@pytest.mark.parametrize("day", [0, 32, -1])
def test_r13_17_renewal_day_must_be_between_1_and_31(day: int) -> None:
    with pytest.raises(ValidationError):
        _account(renewal_day=day)


@pytest.mark.parametrize("kind", ["checking", "cash"])
def test_r13_17_renewal_day_rejected_on_non_benefit_accounts(kind: str) -> None:
    with pytest.raises(ValidationError, match="renewal_day is only allowed on benefit accounts"):
        _account(type=kind, renewal_day=5)


def test_r13_17_changing_type_away_from_benefit_keeps_the_invariant() -> None:
    account = _account(renewal_day=10)
    with pytest.raises(ValidationError, match="only allowed on benefit"):
        account.type = "checking"


def test_r13_17_round_trips_through_json() -> None:
    account = _account(renewal_day=1)
    assert Account.model_validate_json(account.model_dump_json()) == account
