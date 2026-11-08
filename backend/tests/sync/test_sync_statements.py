"""Overlapping statements of the same account (docs/05 "Extratos sobrepostos"; R3.12)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sync_env import Env, make_env, statement

from expense_tracker.review.actions import edit_staged
from expense_tracker.review.confirm import ReviewError

S1 = "extratos/conta/2026-09.pdf"
S2 = "extratos/conta/2026-09b.pdf"
R1 = ("02/09/2026", "PIX ENVIADO LOJA", "20.00")
R2 = ("16/09/2026", "TARIFA PACOTE", "30.00")
R3 = ("25/09/2026", "PIX ENVIADO MERCADO", "40.00")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


def _overlap(env: Env, confirm_first: bool = True) -> None:
    env.put(S1, statement([R1, R2], period=("01/09/2026", "20/09/2026")))
    env.scan()
    if confirm_first:
        env.confirm_all(S1)
    env.put(S2, statement([R2, R3], period=("15/09/2026", "30/09/2026")))
    env.scan()


def _overlap_rows(env: Env, rel: str) -> list[str]:
    return [t.description for t in env.staged(rel) if t.review and t.review.status == "overlap"]


def test_r3_12_overlapping_line_goes_to_staging_as_overlap(env: Env) -> None:
    _overlap(env)
    assert _overlap_rows(env, S2) == ["TARIFA PACOTE"]
    pending = [t for t in env.staged(S2) if t.review and t.review.status == "pending"]
    assert [t.description for t in pending] == ["PIX ENVIADO MERCADO"]
    assert env.entry(S2).status == "pending_review"
    assert env.entry(S1).status == "confirmed"


def test_r3_12_overlap_is_never_confirmed(env: Env) -> None:
    _overlap(env)
    overlap = next(t for t in env.staged(S2) if t.review and t.review.status == "overlap")
    with pytest.raises(ReviewError) as err:
        env.confirm([overlap])
    assert err.value.code == "cannot_confirm"
    env.confirm_all(S2)  # the non-overlap line only
    assert env.entry(S2).status == "confirmed"  # overlap rows do not keep it pending


def test_r3_12_overlapping_line_counted_once(env: Env) -> None:
    _overlap(env)
    assert env.total("2026-09") == "90.00"
    env.confirm_all(S2)
    assert env.total_confirmed("2026-09") == "90.00"


def test_r3_12_overlap_with_pending_owner_keeps_owner_line(env: Env) -> None:
    _overlap(env, confirm_first=False)
    assert env.descs(env.staged(S1)) == {"PIX ENVIADO LOJA", "TARIFA PACOTE"}
    assert env.total("2026-09") == "90.00"


def test_r3_12_removing_owner_transfers_line_to_other_statement(env: Env) -> None:
    env.put(S1, statement([R1, R2], period=("01/09/2026", "20/09/2026")))
    env.scan()
    tarifa = next(t for t in env.staged(S1) if t.description == "TARIFA PACOTE")
    edit_staged(env.repo, tarifa.id, {"note": "pacote anual"}, env.clock.now())
    env.confirm_all(S1)
    env.put(S2, statement([R2, R3], period=("15/09/2026", "30/09/2026")))
    env.scan()
    s2_sha = env.entry(S2).sha256

    env.rm(S1)
    env.scan()

    confirmed = env.confirmed(S2)
    assert [t.description for t in confirmed] == ["TARIFA PACOTE"]  # keeps its confirmation
    moved = confirmed[0]
    assert moved.id == tarifa.id and moved.note == "pacote anual"
    assert moved.source.sha256 == s2_sha and moved.source.path == S2
    assert _overlap_rows(env, S2) == []
    assert env.descs(env.staged(S2)) == {"PIX ENVIADO MERCADO"}
    assert "PIX ENVIADO LOJA" not in {t.description for t in [*env.staged(), *env.confirmed()]}
    ann = env.repo.get("annotations", tarifa.fingerprint)
    assert ann is not None and ann.note == "pacote anual"
    assert env.total("2026-09") == "70.00"


def test_r3_10_statement_receiving_lines_refreshes_status(env: Env) -> None:
    _overlap(env)
    env.rm(S1)
    env.scan()
    assert env.entry(S2).status == "partially_confirmed"


def test_r3_12_removing_the_overlapping_statement_keeps_owner(env: Env) -> None:
    _overlap(env)
    env.rm(S2)
    env.scan()
    assert env.descs(env.confirmed(S1)) == {"PIX ENVIADO LOJA", "TARIFA PACOTE"}
    assert env.staged() == []
    assert env.total("2026-09") == "50.00"
