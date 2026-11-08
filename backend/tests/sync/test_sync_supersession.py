"""Invoice replacement (docs/05 "Substituição de fatura"; R3.11, R4.11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sync_env import CSVCARD, INTER, Env, inter, make_env, open_invoice_csv

from expense_tracker.review.actions import edit_staged
from expense_tracker.services.catalog import Catalog

A_PATH = "faturas/inter/2026-10-parcial.pdf"
B_PATH = "faturas/inter/2026-10-final.pdf"
X = (1, "MERCADO A", "10.00")
Y = (2, "PADARIA B", "5.50")
Z = (3, "FARMACIA C", "7.25")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


def _with_candidate(env: Env, confirm_a: bool = True) -> None:
    env.put(A_PATH, inter(X, Y))
    env.scan()
    if confirm_a:
        env.confirm_all(A_PATH)
    env.put(B_PATH, inter(X, Z))  # Y removed, Z added, X kept
    env.scan()


def test_r3_11_second_invoice_of_same_card_month_is_a_candidate(env: Env) -> None:
    _with_candidate(env)
    a, b = env.entry(A_PATH), env.entry(B_PATH)
    assert b.status == "pending_review"
    assert b.supersedes_candidate == A_PATH
    assert b.card_id == a.card_id == INTER and b.invoice_month == a.invoice_month == "2026-10"
    assert a.status == "confirmed"  # A stays the active document
    assert env.descs(env.staged(B_PATH)) == {"MERCADO A", "FARMACIA C"}
    # calculations keep using A, even counting pending lines
    assert env.total() == "15.50"
    assert env.total_confirmed() == "15.50"


def test_r3_11_candidate_while_a_is_still_pending(env: Env) -> None:
    _with_candidate(env, confirm_a=False)
    assert env.entry(B_PATH).supersedes_candidate == A_PATH
    assert env.descs(env.staged(A_PATH)) == {"MERCADO A", "PADARIA B"}
    assert env.total() == "15.50"


def test_r3_11_never_two_active_documents_for_same_card_month(env: Env) -> None:
    _with_candidate(env)
    third = "faturas/inter/2026-10-reemitida.pdf"
    env.put(third, inter(X, (4, "POSTO D", "50.00")))
    env.scan()
    assert env.entry(third).supersedes_candidate == A_PATH
    assert env.total() == "15.50"


def test_r3_11_approve_replaces_a_with_b_by_fingerprint(env: Env) -> None:
    _with_candidate(env)
    kept_id = next(t.id for t in env.confirmed(A_PATH) if t.description == "MERCADO A")
    b_sha = env.entry(B_PATH).sha256

    out = env.engine.approve_supersession(B_PATH)

    a = env.entry(A_PATH)
    assert a.status == "superseded" and a.superseded_by == B_PATH and not a.active
    assert out.supersedes == A_PATH and out.supersedes_candidate is None
    assert out.status == "partially_confirmed"
    confirmed = env.confirmed(B_PATH)
    assert [t.id for t in confirmed] == [kept_id]  # kept stays confirmed, now pointing to B
    assert confirmed[0].source.sha256 == b_sha
    assert env.descs(env.staged(B_PATH)) == {"FARMACIA C"}
    assert env.lines(A_PATH) == []
    assert "PADARIA B" not in {t.description for t in [*env.staged(), *env.confirmed()]}
    assert env.total() == "17.25"
    assert env.total_confirmed() == "10.00"


def test_r3_11_reject_marks_b_superseded_without_lines(env: Env) -> None:
    _with_candidate(env)
    out = env.engine.reject_supersession(B_PATH)
    assert out.status == "superseded" and out.superseded_by == A_PATH
    assert out.supersedes_candidate is None
    assert env.staged(B_PATH) == []
    assert env.entry(A_PATH).status == "confirmed"
    assert env.total() == "15.50"


def test_r3_11_approve_or_reject_non_candidate_is_refused(env: Env) -> None:
    env.put(A_PATH, inter(X))
    env.scan()
    with pytest.raises(ValueError):
        env.engine.approve_supersession(A_PATH)
    with pytest.raises(ValueError):
        env.engine.reject_supersession(A_PATH)


def test_r3_11_removing_superseded_a_changes_nothing(env: Env) -> None:
    _with_candidate(env)
    env.engine.approve_supersession(B_PATH)
    before = sorted(t.id for t in env.lines(B_PATH))
    env.rm(A_PATH)
    env.scan()
    assert A_PATH not in env.manifest()
    assert sorted(t.id for t in env.lines(B_PATH)) == before
    assert env.entry(B_PATH).active
    assert env.total() == "17.25"


def test_r3_11_removing_b_reactivates_a(env: Env) -> None:
    _with_candidate(env)
    env.engine.approve_supersession(B_PATH)
    env.rm(B_PATH)
    report = env.scan()
    assert report.removed == [B_PATH]
    a = env.entry(A_PATH)
    assert a.active and a.superseded_by is None
    assert env.descs(env.lines(A_PATH)) == {"MERCADO A", "PADARIA B"}
    assert "FARMACIA C" not in {t.description for t in [*env.staged(), *env.confirmed()]}
    assert env.total() == "15.50"


def test_r3_11_removing_b_keeps_confirmation_of_kept_lines(env: Env) -> None:
    _with_candidate(env)
    env.engine.approve_supersession(B_PATH)
    env.confirm_all(B_PATH)
    env.rm(B_PATH)
    env.scan()
    assert env.descs(env.confirmed(A_PATH)) == {"MERCADO A"}
    assert env.descs(env.staged(A_PATH)) == {"PADARIA B"}


def test_r3_11_removing_a_while_b_is_candidate_makes_b_active(env: Env) -> None:
    _with_candidate(env)
    env.rm(A_PATH)
    env.scan()
    b = env.entry(B_PATH)
    assert b.supersedes_candidate is None and b.active
    assert b.status == "pending_review"
    assert env.total() == "17.25"


def test_r3_11_removing_candidate_b_keeps_a(env: Env) -> None:
    _with_candidate(env)
    env.rm(B_PATH)
    env.scan()
    assert B_PATH not in env.manifest()
    assert env.entry(A_PATH).status == "confirmed"
    assert env.staged() == []
    assert env.total() == "15.50"


def test_r3_11_moving_a_keeps_candidate_pointer(env: Env) -> None:
    _with_candidate(env)
    env.mv(A_PATH, "faturas/arquivo/a.pdf")
    env.scan()
    assert env.entry(B_PATH).supersedes_candidate == "faturas/arquivo/a.pdf"
    env.engine.approve_supersession(B_PATH)
    env.mv("faturas/arquivo/a.pdf", "faturas/arquivo/a2.pdf")
    env.scan()
    assert env.entry("faturas/arquivo/a2.pdf").superseded_by == B_PATH


def test_r3_6_moving_a_after_reject_keeps_superseded_by_pointer(env: Env) -> None:
    _with_candidate(env)
    env.engine.reject_supersession(B_PATH)
    env.mv(A_PATH, "faturas/arquivo/a.pdf")
    env.scan()
    assert env.entry(B_PATH).superseded_by == "faturas/arquivo/a.pdf"


def test_r3_6_move_with_subsecond_mtimes_keeps_candidate_pointer(env: Env) -> None:
    env.put(A_PATH, inter(X, Y), mtime_ns=1_790_000_001_123_456_789)
    env.scan()
    env.confirm_all(A_PATH)
    env.put(B_PATH, inter(X, Z), mtime_ns=1_790_000_002_123_456_789)
    env.scan()
    env.mv(A_PATH, "faturas/arquivo/a.pdf")
    env.scan()
    assert env.entry(B_PATH).supersedes_candidate == "faturas/arquivo/a.pdf"


# ---------------------------------------------------------------- R4.11 open invoice


def _csv_card_pdf(*items: tuple[int, str, str]) -> bytes:
    return inter(*items, main="9999", card="9999")


def test_r4_11_open_csv_then_closed_pdf_with_carry_over(env: Env) -> None:
    Catalog(env.repo).create("categories", {"id": "cat_food", "name": "Comida"})
    csv_path, pdf_path = "faturas/y/2026-10.csv", "faturas/y/2026-10-fechada.pdf"
    env.put(
        csv_path,
        open_invoice_csv(
            [
                ("01/09/2026", "MERCADO A", "10,00", ""),
                ("02/09/2026", "PADARIA PAO", "5,50", ""),
            ]
        ),
    )
    env.scan()
    csv_entry = env.entry(csv_path)
    assert csv_entry.format == "csv" and csv_entry.open_invoice
    assert csv_entry.as_of is not None
    assert csv_entry.card_id == CSVCARD and csv_entry.invoice_month == "2026-10"
    fuzzy = next(t for t in env.staged(csv_path) if t.description == "PADARIA PAO")
    edit_staged(env.repo, fuzzy.id, {"category_id": "cat_food", "note": "café"}, env.clock.now())
    env.confirm_all(csv_path)

    # closed invoice: same "MERCADO A" (same fingerprint); bakery printed differently
    env.put(pdf_path, _csv_card_pdf(X, (3, "PADARIA PAO SP", "5.50"), Z))
    env.scan()
    pdf_entry = env.entry(pdf_path)
    assert pdf_entry.supersedes_candidate == csv_path
    assert env.total() == "15.50"

    env.engine.approve_supersession(pdf_path)

    assert env.entry(csv_path).status == "superseded"
    confirmed = {t.description: t for t in env.confirmed(pdf_path)}
    assert set(confirmed) == {"MERCADO A", "PADARIA PAO SP"}
    carried = confirmed["PADARIA PAO SP"]
    assert carried.category_id == "cat_food" and carried.note == "café"
    assert env.descs(env.staged(pdf_path)) == {"FARMACIA C"}
    assert env.entry(pdf_path).status == "partially_confirmed"
    assert env.total() == "22.75"


def test_r4_11_newer_open_csv_replaces_older_open_csv(env: Env) -> None:
    old, new = "faturas/y/2026-10.csv", "faturas/y2/2026-10.csv"
    env.put(old, open_invoice_csv([("01/09/2026", "MERCADO A", "10,00", "")]))
    env.scan()
    env.confirm_all(old)
    env.put(
        new,
        open_invoice_csv(
            [("01/09/2026", "MERCADO A", "10,00", ""), ("05/09/2026", "POSTO", "40,00", "")]
        ),
    )
    env.scan()
    assert env.entry(new).supersedes_candidate == old
    env.engine.approve_supersession(new)
    assert env.descs(env.confirmed(new)) == {"MERCADO A"}
    assert env.descs(env.staged(new)) == {"POSTO"}
