"""Scan events and file statuses (docs/05 "Algoritmo de varredura", "status"; R3.1–R3.10)."""

from __future__ import annotations

import os
import shutil
import types
from decimal import Decimal
from pathlib import Path

import pytest
from sync_env import (
    CAT,
    INTER,
    INTER_ADD,
    ME,
    Env,
    inter,
    inter_invoice,
    make_env,
    statement,
)

from expense_tracker.domain.models import ReviewInfo, Share, Source, Transaction
from expense_tracker.review.actions import edit_staged
from expense_tracker.services.catalog import Catalog
from expense_tracker.sync import engine as engine_mod
from fixtures.files import pdf_bytes

INV = "faturas/inter/2026-10.pdf"
A = (1, "MERCADO A", "10.00")
B = (2, "PADARIA B", "5.50")
C = (3, "FARMACIA C", "7.25")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return make_env(tmp_path)


def _snapshot(env: Env) -> dict[str, list[dict[str, object]]]:
    return {
        name: sorted((i.model_dump(mode="json") for i in env.repo.all(name)), key=lambda d: str(d))
        for name in ("import_manifest", "staging", "transactions", "annotations")
    }


# ---------------------------------------------------------------- NOVO / statuses


def test_r3_2_new_file_goes_to_review_as_pending(env: Env) -> None:
    env.put(INV, inter(A, B))
    report = env.scan()
    assert report.new == [INV]
    entry = env.entry(INV)
    assert entry.status == "pending_review"
    assert entry.active
    assert entry.kind == "fatura" and entry.format == "pdf"
    assert entry.card_id == INTER and entry.invoice_month == "2026-10"
    assert len(entry.sha256) == 64 and entry.size == (env.inbox / INV).stat().st_size
    staged = env.staged(INV)
    assert env.descs(staged) == {"MERCADO A", "PADARIA B"}
    assert all(t.source.sha256 == entry.sha256 and t.source.type == "import" for t in staged)
    assert sorted(entry.tx_fingerprints) == sorted(t.fingerprint for t in staged)
    assert env.confirmed() == []


def test_r3_2_new_statement_resolves_account(env: Env) -> None:
    rel = "extratos/banco/2026-09.pdf"
    env.put(rel, statement([("02/09/2026", "PIX ENVIADO X", "20.00")]))
    env.scan()
    entry = env.entry(rel)
    assert entry.status == "pending_review"
    assert entry.account_id == "acc_main"
    assert str(entry.period_from) == "2026-09-01" and str(entry.period_to) == "2026-09-30"
    assert [t.description for t in env.staged(rel)] == ["PIX ENVIADO X"]


def test_r3_10_confirming_all_lines_marks_file_confirmed(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.confirm_all(INV)
    assert env.entry(INV).status == "confirmed"
    assert env.staged(INV) == []
    assert env.descs(env.confirmed(INV)) == {"MERCADO A", "PADARIA B"}


def test_r3_10_confirming_part_marks_file_partially_confirmed(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.confirm([env.staged(INV)[0]])
    assert env.entry(INV).status == "partially_confirmed"
    assert env.entry(INV).active


def test_r3_10_sum_mismatch_imports_with_warning(env: Env) -> None:
    env.put(INV, inter_invoice([engine_line(A)], total="99,99"))
    env.scan()
    entry = env.entry(INV)
    assert entry.status == "pending_review"
    assert any("sum_mismatch" in w for w in entry.warnings)
    assert len(env.staged(INV)) == 1


def engine_line(item: tuple[int, str, str]) -> object:
    from fixtures.files import Line

    return Line(item[0], 9, 2026, item[1], item[2])


# ---------------------------------------------------------------- ALTERADO


def test_r3_3_changed_file_diffs_by_fingerprint(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.confirm_all(INV)
    kept_before = next(t for t in env.confirmed(INV) if t.description == "MERCADO A")
    old_sha = env.entry(INV).sha256

    env.put(INV, inter(A, C))  # B removed, C added, A kept
    report = env.scan()

    assert report.changed == [INV] and report.new == []
    entry = env.entry(INV)
    assert entry.sha256 != old_sha
    confirmed = env.confirmed(INV)
    assert env.descs(confirmed) == {"MERCADO A"}  # kept stays confirmed
    kept = confirmed[0]
    assert kept.id == kept_before.id and kept.category_id == kept_before.category_id
    assert kept.source.sha256 == entry.sha256
    assert env.descs(env.staged(INV)) == {"FARMACIA C"}  # added goes to review
    all_descs = {t.description for t in [*env.staged(), *env.confirmed()]}
    assert "PADARIA B" not in all_descs  # removed is deleted
    assert not [t for t in [*env.staged(), *env.confirmed()] if t.source.sha256 == old_sha]
    assert entry.status == "partially_confirmed"
    assert sorted(entry.tx_fingerprints) == sorted(t.fingerprint for t in env.lines(INV))


def test_r3_3_changed_file_removes_unconfirmed_lines_too(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.put(INV, inter(A))
    env.scan()
    assert env.descs(env.staged(INV)) == {"MERCADO A"}
    assert env.confirmed() == []
    assert env.entry(INV).status == "pending_review"


def test_r3_3_only_mtime_changed_updates_manifest_without_reprocessing(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    before = _snapshot(env)
    old_mtime = env.entry(INV).mtime
    os.utime(env.inbox / INV, (1_700_000_000, 1_700_000_000))
    report = env.scan()
    assert report.new == report.changed == report.removed == []
    assert env.entry(INV).mtime != old_mtime
    assert env.entry(INV).mtime.timestamp() == 1_700_000_000
    after = _snapshot(env)
    assert after["staging"] == before["staging"]
    assert after["transactions"] == before["transactions"]


# ---------------------------------------------------------------- MOVIDO


def test_r3_6_moved_file_only_updates_path(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.confirm([env.staged(INV)[0]])
    ids = {t.id for t in env.lines(INV)}
    sha = env.entry(INV).sha256
    # if the file were re-parsed now it would become unknown_profile
    for p in env.settings.profiles_dir.glob("*.yaml"):
        p.unlink()
    new = "faturas/outra/renomeada.pdf"
    env.mv(INV, new)

    report = env.scan()

    assert report.moved == [(INV, new)]
    assert report.removed == [] and report.new == []
    assert INV not in env.manifest()
    entry = env.entry(new)
    assert entry.sha256 == sha and entry.status == "partially_confirmed"
    lines = env.lines(new)
    assert {t.id for t in lines} == ids
    assert all(t.source.path == new for t in lines)
    assert len(env.confirmed(new)) == 1 and len(env.staged(new)) == 1


def test_r3_6_move_keeps_duplicate_pointing_to_new_path(env: Env) -> None:
    env.put(INV, inter(A))
    env.scan()
    env.put("faturas/copia.pdf", (env.inbox / INV).read_bytes())
    env.scan()
    env.mv(INV, "faturas/novo.pdf")
    env.scan()
    assert env.entry("faturas/copia.pdf").duplicate_of == "faturas/novo.pdf"


# ---------------------------------------------------------------- DUPLICADO


def test_r3_7_duplicate_is_flagged_and_not_imported(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    dup = "faturas/backup/copia.pdf"
    shutil.copy(env.inbox / INV, env.inbox / "faturas")  # same name elsewhere is a dup too
    env.put(dup, (env.inbox / INV).read_bytes())
    report = env.scan()
    assert sorted(report.duplicate) == sorted([dup, "faturas/2026-10.pdf"])
    entry = env.entry(dup)
    assert entry.status == "duplicate" and not entry.active
    assert entry.duplicate_of == INV
    assert len(env.staged()) == 2  # imported once
    assert env.staged(dup) == []


def test_r3_7_two_new_identical_files_in_same_scan_import_once(env: Env) -> None:
    data = inter(A)
    env.put("faturas/a.pdf", data)
    env.put("faturas/b.pdf", data)
    env.scan()
    statuses = sorted(e.status for e in env.manifest().values())
    assert statuses == ["duplicate", "pending_review"]
    assert len(env.staged()) == 1


def test_r3_7_duplicate_promoted_when_original_leaves(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.confirm_all(INV)
    dup1, dup2 = "faturas/x/c1.pdf", "faturas/x/c2.pdf"
    env.put(dup1, (env.inbox / INV).read_bytes())
    env.put(dup2, (env.inbox / INV).read_bytes())
    env.scan()
    env.rm(INV)

    report = env.scan()

    assert report.removed == [INV]
    promoted = env.entry(dup1)
    assert promoted.active and promoted.duplicate_of is None
    assert env.descs(env.lines(dup1)) == {"MERCADO A", "PADARIA B"}
    assert env.entry(dup2).status == "duplicate"
    assert env.entry(dup2).duplicate_of == dup1
    assert len([*env.staged(), *env.confirmed()]) == 2


# ---------------------------------------------------------------- REMOVIDO / R3.5


def test_r3_4_removed_file_deletes_lines_and_keeps_annotations(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    tx = env.staged(INV)[0]
    edit_staged(env.repo, tx.id, {"note": "minha nota"}, env.clock.now())
    env.confirm_all(INV)
    assert env.total_confirmed() == "15.50"

    env.rm(INV)
    report = env.scan()

    assert report.removed == [INV]
    assert INV not in env.manifest()
    assert env.staged() == [] and env.confirmed() == []
    ann = env.repo.get("annotations", tx.fingerprint)
    assert ann is not None and ann.note == "minha nota"
    assert env.total_confirmed() == "0.00"


def test_r3_5_returning_file_reapplies_my_edits(env: Env) -> None:
    other = Catalog(env.repo).create("categories", {"id": "cat_food", "name": "Comida"})
    data = inter(A, B)
    env.put(INV, data)
    env.scan()
    tx = next(t for t in env.staged(INV) if t.description == "MERCADO A")
    edit_staged(
        env.repo,
        tx.id,
        {
            "category_id": other.id,
            "note": "feira",
            "allocations": [Share(user_id=ME, pct=Decimal("100"))],
        },
        env.clock.now(),
    )
    env.rm(INV)
    env.scan()
    assert env.staged() == []

    env.put("faturas/voltou.pdf", data)  # same hash, another name
    env.scan()

    back = next(t for t in env.staged("faturas/voltou.pdf") if t.description == "MERCADO A")
    assert back.fingerprint == tx.fingerprint
    assert back.category_id == "cat_food"
    assert back.note == "feira"
    assert back.allocation_origin == "manual"
    untouched = next(t for t in env.staged("faturas/voltou.pdf") if t.description == "PADARIA B")
    assert untouched.category_id == CAT


def test_r3_5_same_lines_with_different_hash_reapply_edits(env: Env) -> None:
    Catalog(env.repo).create("categories", {"id": "cat_food", "name": "Comida"})
    env.put(INV, inter(A))
    env.scan()
    tx = env.staged(INV)[0]
    edit_staged(env.repo, tx.id, {"category_id": "cat_food"}, env.clock.now())
    env.rm(INV)
    env.scan()
    env.put(INV, inter_invoice([engine_line(A)], holder="OUTRO TITULAR QUALQUER"))
    env.scan()
    (back,) = env.staged(INV)
    assert back.fingerprint == tx.fingerprint and back.category_id == "cat_food"


# ---------------------------------------------------------------- failures / statuses


def test_r3_10_unknown_profile(env: Env) -> None:
    rel = "faturas/desconhecido.pdf"
    env.put(rel, pdf_bytes([["Banco Nenhum", "Nada para ver aqui"]]))
    env.scan()
    entry = env.entry(rel)
    assert entry.status == "unknown_profile" and not entry.active
    assert env.staged() == []


def test_r3_10_wrong_password_is_error_and_nothing_imported(tmp_path: Path) -> None:
    env = make_env(tmp_path, passwords={"inter": "errada"})
    from fixtures.files import pdf_bytes as render

    rel = "extratos/protegido.pdf"
    lines = [
        "BANCO TESTE",
        "Extrato de conta",
        "Conta 12345-6",
        "Periodo 01/09/2026 a 30/09/2026",
        "Movimentacoes",
        "02/09/2026 PIX ENVIADO X -20,00",
        "Saldo final 0,00",
    ]
    env.put(rel, render([lines], password="certa"))
    env.scan()
    entry = env.entry(rel)
    assert entry.status == "error" and not entry.active
    assert entry.error and "senha" in entry.error
    assert env.staged() == []

    # after saving the right password the file can be reprocessed
    env.settings.secrets_file.write_text("conta: certa\n", encoding="utf-8")
    assert env.engine.reprocess_failed() == [rel]
    assert env.entry(rel).status == "pending_review"
    assert len(env.staged(rel)) == 1


def test_r3_10_profile_with_runtime_error_is_error(env: Env) -> None:
    prof = env.settings.profiles_dir / "inter-fatura.yaml"
    text = prof.read_text(encoding="utf-8").replace(
        "date_format: '%d de %b. %Y'", "date_format: '%Y'"
    )
    prof.write_text(text, encoding="utf-8")
    env.put(INV, inter(A))
    env.scan()
    entry = env.entry(INV)
    assert entry.status == "error"
    assert entry.error
    assert env.staged() == []


def test_r3_10_broken_profile_reports_validation_error(env: Env) -> None:
    prof = env.settings.profiles_dir / "inter-fatura.yaml"
    prof.write_text(prof.read_text(encoding="utf-8") + "\nunknown_field: 1\n", encoding="utf-8")
    env.put(INV, inter(A))
    env.scan()
    entry = env.entry(INV)
    assert entry.status == "error"
    assert entry.error and "unknown_field" in entry.error


def test_r3_8_profile_saved_reprocesses_unknown_profile(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    saved = (env.settings.profiles_dir / "banco-teste-extrato.yaml").read_text(encoding="utf-8")
    (env.settings.profiles_dir / "banco-teste-extrato.yaml").unlink()
    rel = "extratos/x.pdf"
    env.put(rel, statement([("02/09/2026", "PIX ENVIADO X", "20.00")]))
    env.scan()
    assert env.entry(rel).status == "unknown_profile"
    (env.settings.profiles_dir / "banco-teste-extrato.yaml").write_text(saved, encoding="utf-8")
    assert env.engine.reprocess_failed() == [rel]
    assert env.entry(rel).status == "pending_review"


def test_r4_8_awaiting_card_until_choice_then_reprocessed(env: Env) -> None:
    Catalog(env.repo).create(
        "cards",
        {
            "id": "card_inter2",
            "name": "Inter 2",
            "owners": [{"user_id": ME, "pct": "100"}],
            "responsible_user_id": ME,
            "billing_history": [{"from_month": "2026-01", "closing_day": 5, "due_day": 15}],
            "profile_id": "inter-fatura",
        },
    )
    rel = "faturas/sem-cartao.pdf"
    env.put(rel, inter(A, main="4321", card="4321"))
    env.scan()
    entry = env.entry(rel)
    assert entry.status == "awaiting_card" and not entry.active
    assert entry.error
    assert env.staged() == []  # nothing goes to review before the choice

    out = env.engine.choose_owner(rel, INTER, None, None)

    assert out.status == "pending_review" and out.card_id == INTER
    assert len(env.staged(rel)) == 1
    # the choice is remembered: same card hint in another file resolves directly
    env.put("faturas/sem-cartao-2.pdf", inter(B, main="4321", card="4321"))
    env.scan()
    assert env.entry("faturas/sem-cartao-2.pdf").card_id == INTER


def test_r4_8_statement_awaiting_account(env: Env) -> None:
    Catalog(env.repo).create(
        "accounts",
        {
            "id": "acc_2",
            "name": "Outra",
            "owners": [{"user_id": ME, "pct": "100"}],
            "responsible_user_id": ME,
            "profile_id": "banco-teste-extrato",
        },
    )
    rel = "extratos/x.pdf"
    env.put(rel, statement([("02/09/2026", "PIX ENVIADO X", "20.00")], account="999-9"))
    env.scan()
    assert env.entry(rel).status == "awaiting_card"
    out = env.engine.choose_owner(rel, None, "acc_2", None)
    assert out.status == "pending_review" and out.account_id == "acc_2"


def test_r3_3_reprocess_active_file_keeps_confirmations(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.confirm([env.staged(INV)[0]])
    out = env.engine.reprocess(INV)
    assert len(env.confirmed(INV)) == 1 and len(env.staged(INV)) == 1
    assert out.status == "partially_confirmed"


def test_r3_10_user_action_on_unknown_path_raises(env: Env) -> None:
    with pytest.raises(KeyError):
        env.engine.reprocess("faturas/nao-existe.pdf")


# ---------------------------------------------------------------- ignored files


def test_r3_1_ignored_files(env: Env, tmp_path: Path) -> None:
    data = inter(A)
    outside = tmp_path / "fora.pdf"
    outside.write_bytes(inter(B))
    for rel in (
        "faturas/.oculto.pdf",
        "faturas/.pasta/arq.pdf",
        "faturas/~temp.pdf",
        "faturas/baixando.pdf.part",
        "faturas/baixando.crdownload",
        "faturas/notas.txt",
        "outros/fatura.pdf",
        "solto.pdf",
    ):
        env.put(rel, data)
    (env.inbox / "faturas" / "link-fora.pdf").symlink_to(outside)
    report = env.scan()
    assert report.new == []
    assert env.manifest() == {}
    assert env.staged() == []


def test_r3_1_csv_and_symlink_inside_inbox_are_read(env: Env) -> None:
    env.put(INV, inter(A))
    (env.inbox / "faturas" / "link.pdf").symlink_to(env.inbox / INV)
    env.scan()
    assert env.entry(INV).active
    assert env.entry("faturas/link.pdf").status == "duplicate"


def test_r3_1_missing_inbox_is_empty(env: Env) -> None:
    shutil.rmtree(env.inbox)
    assert env.scan().new == []


def test_r3_1_directory_with_pdf_suffix_is_ignored(env: Env) -> None:
    (env.inbox / "faturas" / "pasta.pdf").mkdir()
    env.put("faturas/pasta.pdf/dentro.pdf", inter(A))
    env.scan()
    assert list(env.manifest()) == ["faturas/pasta.pdf/dentro.pdf"]


@pytest.mark.parametrize("content", ["::: not yaml :::\n  - [", "- just\n- a list\n"])
def test_r3_10_unreadable_secrets_mean_no_password(tmp_path: Path, content: str) -> None:
    env = make_env(tmp_path)
    env.settings.secrets_file.write_text(content, encoding="utf-8")
    rel = "extratos/protegido.pdf"
    lines = ["BANCO TESTE", "Extrato de conta", "Conta 12345-6", "Periodo 01/09/2026 a 30/09/2026"]
    env.put(rel, pdf_bytes([[*lines, "Movimentacoes", "Saldo final 0,00"]], password="x"))
    env.scan()
    assert env.entry(rel).status == "error"


def test_r4_8_csv_without_hint_awaits_card_and_month_choice(env: Env) -> None:
    from fixtures.files import open_invoice_csv

    Catalog(env.repo).create(
        "cards",
        {
            "id": "card_y2",
            "name": "Banco Y 2",
            "owners": [{"user_id": ME, "pct": "100"}],
            "responsible_user_id": ME,
            "billing_history": [{"from_month": "2026-01", "closing_day": 5, "due_day": 15}],
            "profile_id": "banco-y-fatura-aberta-csv",
        },
    )
    rel = "faturas/y/aberta-2026-10.csv"
    env.put(rel, open_invoice_csv([("01/09/2026", "MERCADO A", "10,00", "")]))
    env.scan()
    assert env.entry(rel).status == "awaiting_card"
    out = env.engine.choose_owner(rel, "card_y2", None, "2026-10")
    assert out.status == "pending_review" and out.card_id == "card_y2"
    assert out.invoice_month == "2026-10"


def test_staged_review_defaults() -> None:
    tx = Transaction(
        id="tx_1",
        source=Source(type="manual"),
        purchase_date=engine_mod.datetime(2026, 9, 1).date(),
        invoice_month="2026-10",
        description="X",
        amount="1.00",
        card_id=INTER,
    )
    assert engine_mod.staged_review(tx) == ReviewInfo()


# ---------------------------------------------------------------- R3.9 still copying


def test_r3_9_waits_for_stable_size_before_processing(tmp_path: Path) -> None:
    calls: list[float] = []
    holder: dict[str, Env] = {}
    final = inter(A, B)

    def growing(seconds: float) -> None:
        calls.append(seconds)
        if len(calls) == 1:  # the copy finishes during the first wait
            (holder["env"].inbox / INV).write_bytes(final)

    env = make_env(tmp_path, stable_wait=2, sleep=growing)
    holder["env"] = env
    env.put(INV, final[: len(final) // 2])
    env.scan()
    assert calls[:2] == [2, 2]
    entry = env.entry(INV)
    assert entry.size == len(final)
    assert entry.status == "pending_review" and len(env.staged(INV)) == 2


def test_r3_9_unstable_file_is_skipped_until_next_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter(range(0, 10_000, 30))
    monkeypatch.setattr(engine_mod, "time", types.SimpleNamespace(monotonic=lambda: next(ticks)))
    holder: dict[str, Env] = {}

    def still_copying(_: float) -> None:
        with open(holder["env"].inbox / INV, "ab") as fh:
            fh.write(b"0")

    env = make_env(tmp_path, stable_wait=2, sleep=still_copying)
    holder["env"] = env
    env.put(INV, inter(A))
    report = env.scan()
    assert report.unstable == [INV]
    assert env.manifest() == {} and env.staged() == []

    env.engine.sleep = lambda _: None  # copy finished
    env.put(INV, inter(A))
    report = env.scan()
    assert report.new == [INV]


def test_r3_9_file_vanishing_while_waiting_is_unstable(tmp_path: Path) -> None:
    holder: dict[str, Env] = {}

    def vanish(_: float) -> None:
        holder["env"].rm(INV)

    env = make_env(tmp_path, stable_wait=1, sleep=vanish)
    holder["env"] = env
    env.put(INV, inter(A))
    assert env.scan().unstable == [INV]


def test_r3_9_unreadable_file_is_reported(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.put(INV, inter(A))

    def boom(_: Path) -> str:
        raise PermissionError("denied")

    monkeypatch.setattr(engine_mod, "sha256_file", boom)
    report = env.scan()
    assert report.errors and INV in report.errors[0]
    assert env.manifest() == {}


# ---------------------------------------------------------------- guarantees


def test_r3_8_scan_is_idempotent(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.put("extratos/x.pdf", statement([("02/09/2026", "PIX ENVIADO X", "20.00")]))
    env.scan()
    env.confirm([env.staged(INV)[0]])
    before = _snapshot(env)
    report = env.scan()
    assert all(not v for v in report.as_dict().values())
    assert _snapshot(env) == before
    assert env.engine.last_report is report and env.engine.last_scan == env.clock.now()


def test_r3_8_orphan_staging_is_dropped_on_scan(env: Env) -> None:
    env.put(INV, inter(A))
    env.scan()
    orphan = Transaction(
        id="tx_orphan",
        fingerprint="fp_orphan",
        source=Source(type="import", sha256="f" * 64, path="faturas/sumiu.pdf"),
        purchase_date=env.clock.today(),
        invoice_month="2026-10",
        description="ORFAO",
        amount="1.00",
        card_id=INTER_ADD,
        review=ReviewInfo(),
    )
    env.repo.put("staging", orphan)
    env.repo.put("transactions", orphan.model_copy(update={"id": "tx_orphan2", "review": None}))
    env.scan()
    assert env.repo.get("staging", "tx_orphan") is None
    assert env.repo.get("transactions", "tx_orphan2") is None
    assert len(env.staged(INV)) == 1


def test_r3_8_crash_before_manifest_write_is_recovered(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    ids = {t.id for t in env.staged(INV)}
    # simulate a crash after the data was written but before the manifest was
    env.repo.delete("import_manifest", INV)
    report = env.scan()
    assert report.new == [INV]
    assert {t.id for t in env.staged(INV)} == ids
    assert len(env.staged()) == 2


def test_r3_8_crash_after_confirmation_does_not_duplicate(env: Env) -> None:
    env.put(INV, inter(A, B))
    env.scan()
    env.confirm_all(INV)
    # manifest entry lost, data kept: rescan imports again without duplicating lines
    env.repo.delete("import_manifest", INV)
    env.scan()
    fps = [t.fingerprint for t in [*env.staged(), *env.confirmed()]]
    assert len(fps) == len(set(fps)) == 2
