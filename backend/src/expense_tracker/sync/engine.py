"""Inbox synchronization engine (docs/05-sincronizacao.md).

``SyncEngine.scan()`` is idempotent and safe to call any time; the service layer serializes calls
through a single-consumer queue.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from expense_tracker.clock import Clock
from expense_tracker.config import Settings
from expense_tracker.domain.documents import CardChoice, ManifestEntry
from expense_tracker.domain.models import ReviewInfo, Transaction
from expense_tracker.domain.normalize import folder_key, folder_name, similarity
from expense_tracker.importing import parse_file
from expense_tracker.profiles import load_all, load_profiles
from expense_tracker.review.confirm import (
    Confirmer,
    move_lines,
    refresh_status,
    relink_on_return,
    remove_lines,
)
from expense_tracker.review.staging import (
    Identified,
    OwnerUnresolved,
    account_by_folder,
    card_by_folder,
    identify,
    stage_document,
)
from expense_tracker.services.errors import new_id
from expense_tracker.storage import Repository

log = logging.getLogger("expense_tracker.sync")

IGNORED_PREFIXES = (".", "~")
IGNORED_SUFFIXES = (".part", ".crdownload", ".tmp")
ALLOWED_SUFFIXES = (".pdf", ".csv")


@dataclass
class FileInfo:
    path: str  # relative to inbox
    size: int
    mtime: float


@dataclass
class ScanReport:
    new: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    moved: list[tuple[str, str]] = field(default_factory=list)
    duplicate: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unstable: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _kind_for(rel: str) -> str | None:
    top = rel.split("/", 1)[0]
    return {"faturas": "fatura", "extratos": "extrato"}.get(top)


class SyncEngine:
    def __init__(
        self,
        repo: Repository,
        settings: Settings,
        clock: Clock,
        stable_wait: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.clock = clock
        self.stable_wait = stable_wait
        self.sleep = sleep
        self.last_scan: datetime | None = None
        self._backed_up = False
        self._retried_failed = False
        self.last_report: ScanReport | None = None

    # ------------------------------------------------------------------ disk

    def ensure_folders(self) -> list[str]:
        """One inbox folder per main card (``faturas/<name lowercase>``) and per account
        (``extratos/<name lowercase>``), so the operator knows where to drop each file."""
        created = []
        targets = [("faturas", c.name) for c in self.repo.all("cards") if not c.parent_card_id]
        targets += [("extratos", a.name) for a in self.repo.all("accounts") if a.type != "cash"]
        root = self.settings.inbox_dir
        for top, name in targets:
            base = root / top
            if any(folder_key(p.name) == folder_key(name) for p in base.glob("*") if p.is_dir()):
                continue
            path = base / folder_name(name)
            try:
                path.mkdir(parents=True, exist_ok=True)
                created.append(str(path.relative_to(root)))
            except OSError as exc:  # read-only inbox mount: never fail the request
                log.warning("cannot create inbox folder: %s", type(exc).__name__)
        return created

    def list_inbox(self) -> dict[str, FileInfo]:
        root = self.settings.inbox_dir.resolve()
        out: dict[str, FileInfo] = {}
        if not root.is_dir():
            return out
        for path in sorted(root.rglob("*")):
            rel_parts = path.relative_to(root).parts
            if any(p.startswith(IGNORED_PREFIXES) for p in rel_parts):
                continue
            if path.name.endswith(IGNORED_SUFFIXES) or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if path.is_symlink():
                target = path.resolve()
                if not target.is_relative_to(root):
                    continue  # docs/13: symlinks outside inbox are ignored
            if not path.is_file():
                continue
            rel = "/".join(rel_parts)
            if _kind_for(rel) is None:
                continue
            st = path.stat()
            out[rel] = FileInfo(rel, st.st_size, st.st_mtime)
        return out

    def _stable(self, info: FileInfo) -> bool:
        """R3.9: wait until the size stops changing (two reads ``stable_wait`` apart)."""
        if self.stable_wait <= 0:
            return True
        path = self.settings.inbox_dir / info.path
        deadline = time.monotonic() + 60
        size = info.size
        while time.monotonic() < deadline:
            self.sleep(self.stable_wait)
            try:
                now = path.stat().st_size
            except FileNotFoundError:
                return False
            if now == size:
                return True
            size = now
        return False

    def _passwords(self) -> list[str]:
        path = self.settings.secrets_file
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return []
        if not isinstance(data, dict):
            return []
        return [str(v) for v in data.values() if v is not None]

    # ------------------------------------------------------------------ scan

    def _backup_once(self) -> None:
        """One automatic backup per scan, before the first change (not one per file)."""
        if not self._backed_up:
            self.repo.backup(reason="import")
            self._backed_up = True

    def scan(self) -> ScanReport:
        self._backed_up = False
        self.ensure_folders()
        report = ScanReport()
        disk = self.list_inbox()
        manifest: dict[str, ManifestEntry] = {e.path: e for e in self.repo.all("import_manifest")}
        self._drop_orphans(manifest)
        seen_sha: dict[str, str] = {}
        handled_old: set[str] = set()
        for rel, info in disk.items():
            entry = manifest.get(rel)
            if (
                entry is not None
                and entry.size == info.size
                and abs(entry.mtime.timestamp() - info.mtime) < 2e-6  # datetime keeps µs only
            ):
                seen_sha[entry.sha256] = rel
                continue
            if not self._stable(info):
                report.unstable.append(rel)
                continue
            try:
                sha = sha256_file(self.settings.inbox_dir / rel)
            except OSError as exc:
                report.errors.append(f"{rel}: {exc}")
                continue
            mtime = datetime.fromtimestamp(info.mtime, tz=self.clock.now().tzinfo)
            size = (self.settings.inbox_dir / rel).stat().st_size
            if entry is not None and entry.sha256 == sha:
                fresh = self.repo.get("import_manifest", rel) or entry  # snapshot may be stale
                self.repo.put(
                    "import_manifest", fresh.model_copy(update={"mtime": mtime, "size": size})
                )
                seen_sha[sha] = rel
                continue
            same = [e for e in manifest.values() if e.sha256 == sha and e.path != rel]
            moved_from = next(
                (e for e in same if e.path not in disk and e.path not in handled_old), None
            )
            if entry is None and moved_from is not None:
                self._move(moved_from, rel, size, mtime)
                handled_old.add(moved_from.path)
                report.moved.append((moved_from.path, rel))
                seen_sha[sha] = rel
            elif entry is None and (same or sha in seen_sha):
                original = same[0].path if same else seen_sha[sha]
                self._put_entry(
                    ManifestEntry(
                        path=rel,
                        sha256=sha,
                        size=size,
                        mtime=mtime,
                        kind=_kind_for(rel) or "fatura",  # type: ignore[arg-type]
                        status="duplicate",
                        duplicate_of=original,
                    )
                )
                report.duplicate.append(rel)
            elif entry is not None:
                self._changed(entry, sha, size, mtime)
                report.changed.append(rel)
                seen_sha[sha] = rel
            else:
                self._new(rel, sha, size, mtime)
                report.new.append(rel)
                seen_sha[sha] = rel
        for path, entry in manifest.items():
            if path not in disk and path not in handled_old:
                self._removed(entry)
                report.removed.append(path)
        if not self._retried_failed:
            # first scan of this process: files that failed with an older app/profile set
            # (e.g. before built-in profiles or folder matching) get a new chance
            self._retried_failed = True
            self.reprocess_failed(("unknown_profile", "awaiting_card", "error"))
        self.last_scan = self.clock.now()
        self.last_report = report
        return report

    def _drop_orphans(self, manifest: dict[str, ManifestEntry]) -> None:
        """Invariant 2: imported lines must belong to an active manifest entry (crash recovery)."""
        active = {e.sha256 for e in manifest.values() if e.active}
        known_sha = {e.sha256 for e in manifest.values()}
        known_path = set(manifest)
        with self.repo.batch():
            for coll in ("staging", "transactions"):
                for tx in self.repo.all(coll):
                    if tx.source.type == "import" and tx.source.sha256 not in active:
                        # a confirmed line is never dropped while its file is still known:
                        # a crash between writing transactions and the manifest leaves the new
                        # sha in the lines and the old one in the manifest (docs/05 "Garantias")
                        if coll == "transactions" and (
                            tx.source.sha256 in known_sha or tx.source.path in known_path
                        ):
                            continue
                        self.repo.delete(coll, tx.id)

    # ------------------------------------------------------------------ events

    def _put_entry(self, entry: ManifestEntry) -> None:
        self.repo.put("import_manifest", entry)

    def _move(self, old: ManifestEntry, rel: str, size: int, mtime: datetime) -> None:
        with self.repo.batch():
            for coll in ("transactions", "staging"):
                for tx in self.repo.all(coll):
                    if tx.source.sha256 == old.sha256 and tx.source.path == old.path:
                        self.repo.put(
                            coll,
                            tx.model_copy(
                                update={"source": tx.source.model_copy(update={"path": rel})}
                            ),
                        )
            for e in self.repo.all("import_manifest"):
                if e.duplicate_of == old.path:
                    self.repo.put("import_manifest", e.model_copy(update={"duplicate_of": rel}))
                if e.superseded_by == old.path:
                    self.repo.put("import_manifest", e.model_copy(update={"superseded_by": rel}))
                if e.supersedes_candidate == old.path:
                    self.repo.put(
                        "import_manifest", e.model_copy(update={"supersedes_candidate": rel})
                    )
            self.repo.delete("import_manifest", old.path)
            self.repo.put(
                "import_manifest",
                old.model_copy(update={"path": rel, "size": size, "mtime": mtime}),
            )

    def _parse(self, rel: str, forced_profile: str | None = None) -> Any:
        profiles = load_all(self.settings.profiles_dir, self.settings.examples_dir)
        kind = _kind_for(rel) or "fatura"
        path = self.settings.inbox_dir / rel
        mtime_date = datetime.fromtimestamp(path.stat().st_mtime, tz=self.clock.now().tzinfo).date()
        return parse_file(
            path,
            kind,
            profiles,
            self._passwords(),
            self.settings.parse_timeout_seconds,
            forced_profile,
            mtime_date,
        )

    def _base_entry(self, rel: str, sha: str, size: int, mtime: datetime) -> ManifestEntry:
        return ManifestEntry(
            path=rel,
            sha256=sha,
            size=size,
            mtime=mtime,
            kind=_kind_for(rel) or "fatura",  # type: ignore[arg-type]
            format="csv" if rel.lower().endswith(".csv") else "pdf",
            imported_at=self.clock.now(),
        )

    def _new(
        self, rel: str, sha: str, size: int, mtime: datetime, keep: ManifestEntry | None = None
    ) -> ManifestEntry:
        """NOVO: parse → identify → (supersession check) → staging. Manifest written last."""
        self._backup_once()
        entry = self._base_entry(rel, sha, size, mtime)
        if keep is not None:
            entry = entry.model_copy(update={"imported_at": keep.imported_at})
        outcome = self._parse(rel)
        if outcome.status == "unknown_profile":
            # the folder names a card/account with a configured profile: use it
            owner = (
                card_by_folder(self.repo.all("cards"), rel)
                if entry.kind == "fatura"
                else account_by_folder(self.repo.all("accounts"), rel)
            )
            if owner is not None and owner.profile_id:
                outcome = self._parse(rel, forced_profile=owner.profile_id)
        if outcome.status != "ok" or outcome.result is None:
            status = "unknown_profile" if outcome.status == "unknown_profile" else "error"
            error = outcome.error
            broken = load_profiles(self.settings.profiles_dir).errors
            if status == "unknown_profile" and broken:
                # docs/05: a broken profile is reported as an error with its validation message
                status = "error"
                error = "perfil inválido: " + "; ".join(f"{k}: {v}" for k, v in broken.items())
            entry = entry.model_copy(update={"status": status, "error": error})
            self._put_entry(entry)
            return entry
        result = outcome.result
        entry = entry.model_copy(
            update={
                "profile_id": outcome.profile_id,
                "card_hint": result.card_hint or result.account_hint,
                "total": result.total,
                "amount_due": result.amount_due,
                "due_date": result.due_date,
                "closing_date": result.closing_date,
                "open_invoice": result.open_invoice,
                "as_of": result.as_of or (mtime.date() if result.open_invoice else None),
                "period_from": result.period_from,
                "period_to": result.period_to,
                "invoice_month": result.invoice_month,
            }
        )
        try:
            ident = identify(self.repo, entry, result)
        except OwnerUnresolved as exc:
            entry = entry.model_copy(update={"status": "awaiting_card", "error": str(exc)})
            self._put_entry(entry)
            return entry
        entry = entry.model_copy(
            update={
                "card_id": ident.card_id,
                "account_id": ident.account_id,
                "invoice_month": ident.invoice_month,
                "status": "pending_review",
                "error": None,
            }
        )
        if result.kind == "fatura":
            current = self._active_invoice(ident.card_id, ident.invoice_month, exclude=rel)
            if current is not None:
                entry = entry.model_copy(update={"supersedes_candidate": current.path})
        staged, recon = stage_document(self.repo, entry, result, ident, self.clock.now())
        return self._write_staged(
            entry, staged, result.warnings + ident.warnings + recon.warnings, ident
        )

    def _write_staged(
        self,
        entry: ManifestEntry,
        staged: list[Transaction],
        warnings: list[str],
        ident: Identified,
    ) -> ManifestEntry:
        confirmed = {t.fingerprint: t for t in self.repo.all("transactions") if t.fingerprint}
        other_active = self._fps_of_other_docs(entry)
        with self.repo.batch():
            for tx in staged:
                if (
                    tx.fingerprint in confirmed
                    and confirmed[tx.fingerprint].source.sha256 == entry.sha256
                ):
                    continue  # already confirmed (re-import after a crash)
                if entry.kind == "extrato" and tx.fingerprint in other_active:
                    assert tx.review is not None
                    tx = tx.model_copy(
                        update={"review": tx.review.model_copy(update={"status": "overlap"})}
                    )
                self.repo.put("staging", tx)
            fps = [t.fingerprint for t in staged if t.fingerprint]
            relink_on_return(self.repo, set(fps))
            entry = entry.model_copy(
                update={"tx_fingerprints": fps, "warnings": list(dict.fromkeys(warnings))}
            )
            self._put_entry(entry)
            refresh_status(self.repo, entry.sha256)
        _ = ident
        stored: ManifestEntry | None = self.repo.get("import_manifest", entry.path)
        return stored or entry

    def _fps_of_other_docs(self, entry: ManifestEntry) -> set[str]:
        out = set()
        for tx in [*self.repo.all("transactions"), *self.repo.all("staging")]:
            if (
                tx.source.type == "import"
                and tx.source.sha256 != entry.sha256
                and tx.fingerprint
                and (tx.account_id == entry.account_id)
                and (tx.review is None or tx.review.status != "overlap")
            ):
                out.add(tx.fingerprint)
        return out

    def _active_invoice(
        self, card_id: str | None, month: str | None, exclude: str
    ) -> ManifestEntry | None:
        entries: list[ManifestEntry] = self.repo.all("import_manifest")
        for e in entries:
            if (
                e.path != exclude
                and e.kind == "fatura"
                and e.active
                and e.card_id == card_id
                and e.invoice_month == month
                and not e.supersedes_candidate
            ):
                return e
        return None

    def _lines_of(self, sha: str) -> list[Transaction]:
        return [
            t
            for t in [*self.repo.all("transactions"), *self.repo.all("staging")]
            if t.source.sha256 == sha
        ]

    def _changed(self, old: ManifestEntry, sha: str, size: int, mtime: datetime) -> None:
        """ALTERADO: reparse and diff by fingerprint (kept lines keep their confirmation).

        Also used by "reprocess" with the same sha (e.g. after registering a card final)."""
        old_lines = self._lines_of(old.sha256)
        if old.active and sha != old.sha256:
            probe = self._parse(old.path)
            if probe.status != "ok":
                # docs/05: a transient failure (wrong password, timeout) never deletes what was
                # confirmed; the previous version stays active with a warning
                warning = f"nova versão não pôde ser lida: {probe.error or probe.status}"
                self.repo.put(
                    "import_manifest",
                    old.model_copy(
                        update={"warnings": list(dict.fromkeys([*old.warnings, warning]))}
                    ),
                )
                return
        with self.repo.batch():
            self.repo.delete("import_manifest", old.path)
            new_entry = self._new(old.path, sha, size, mtime, keep=old)
            self._carry_over(old_lines, new_entry)
            refresh_status(self.repo, sha)

    def _carry_over(self, old_lines: list[Transaction], new_entry: ManifestEntry) -> None:
        """Move the confirmed lines of an old version to the new one (diff by fingerprint).

        Kept + confirmed: the confirmed transaction now points to the new document and the newly
        staged copy is dropped. Kept + pending: the new staged copy wins (my edits live in the
        annotations). Removed: deleted with cascade.
        """
        new_fps = set(new_entry.tx_fingerprints)
        old_fps = {t.fingerprint for t in old_lines if t.fingerprint}
        for old_tx in old_lines:
            if old_tx.fingerprint not in new_fps:
                continue
            if old_tx.review is None:  # confirmed
                for staged in self.repo.all("staging"):
                    if (
                        staged.source.sha256 == new_entry.sha256
                        and staged.fingerprint == old_tx.fingerprint
                    ):
                        self.repo.delete("staging", staged.id)
                self.repo.put(
                    "transactions",
                    old_tx.model_copy(
                        update={
                            "source": old_tx.source.model_copy(
                                update={"sha256": new_entry.sha256, "path": new_entry.path}
                            )
                        }
                    ),
                )
            elif old_tx.source.sha256 != new_entry.sha256:
                self.repo.delete("staging", old_tx.id)
        removed = {f for f in old_fps - new_fps if f}
        for sha in {t.source.sha256 for t in old_lines if t.source.sha256}:
            if sha != new_entry.sha256:
                remove_lines(self.repo, removed, self.clock.now(), sha=sha)
        if any(t.source.sha256 == new_entry.sha256 for t in old_lines):
            remove_lines(self.repo, removed, self.clock.now(), sha=new_entry.sha256)

    def _removed(self, entry: ManifestEntry) -> None:
        """REMOVIDO: delete its lines (cascade), keep annotations; promote duplicates;
        reactivate the document it had replaced (diff B -> A keeps confirmations)."""
        twin = next(
            (
                e
                for e in self.repo.all("import_manifest")
                if e.path != entry.path
                and e.sha256 == entry.sha256
                and (self.settings.inbox_dir / e.path).is_file()
            ),
            None,
        )
        if twin is not None:
            self._hand_over(entry, twin)
            return
        self._backup_once()
        receivers: set[str] = set()
        previous = next(
            (
                e
                for e in self.repo.all("import_manifest")
                if e.superseded_by == entry.path
                and e.status == "superseded"
                and (self.settings.inbox_dir / e.path).is_file()
            ),
            None,
        )
        with self.repo.batch():
            lines = self._lines_of(entry.sha256)
            fps: set[str] = {t.fingerprint for t in lines if t.fingerprint}
            # extratos: lines also present (as overlap) in another document move to it
            overlap_rows = {
                t.fingerprint: t
                for t in self.repo.all("staging")
                if t.review and t.review.status == "overlap" and t.source.sha256 != entry.sha256
            }
            for tx in lines:
                other = overlap_rows.get(tx.fingerprint)
                if other is None or (tx.review is not None and tx.review.status == "overlap"):
                    continue
                self.repo.delete("staging", other.id)
                coll = "transactions" if tx.review is None else "staging"
                self.repo.delete(coll, tx.id)
                moved = tx.model_copy(update={"source": other.source})
                if coll == "staging":
                    moved = moved.model_copy(update={"id": other.id})
                self.repo.put(coll, moved)
                if other.source.sha256:
                    receivers.add(other.source.sha256)
                if tx.fingerprint:
                    fps.discard(tx.fingerprint)
            self.repo.delete("import_manifest", entry.path)
            if previous is not None:
                remaining = [t for t in self._lines_of(entry.sha256)]
                self.repo.delete("import_manifest", previous.path)
                revived = self._new(
                    previous.path, previous.sha256, previous.size, previous.mtime, keep=previous
                )
                self._carry_over(remaining, revived)
                receivers.add(revived.sha256)
            else:
                remove_lines(self.repo, fps, self.clock.now(), sha=entry.sha256)
            for coll in ("staging", "transactions"):
                for tx in self.repo.all(coll):
                    if tx.source.sha256 == entry.sha256:
                        self.repo.delete(coll, tx.id)
            for e in self.repo.all("import_manifest"):
                if e.supersedes_candidate == entry.path:
                    self.repo.put(
                        "import_manifest", e.model_copy(update={"supersedes_candidate": None})
                    )
                    receivers.add(e.sha256)
            for sha in receivers:
                refresh_status(self.repo, sha)

    def _hand_over(self, entry: ManifestEntry, twin: ManifestEntry) -> None:
        """The removed file has a byte-identical copy still in the inbox: the copy takes over the
        lines, confirmations and status (like MOVIDO, docs/05) instead of re-importing."""
        with self.repo.batch():
            for coll in ("transactions", "staging"):
                for tx in self.repo.all(coll):
                    if tx.source.sha256 == entry.sha256 and tx.source.path == entry.path:
                        self.repo.put(
                            coll,
                            tx.model_copy(
                                update={"source": tx.source.model_copy(update={"path": twin.path})}
                            ),
                        )
            if twin.status == "duplicate":
                promoted = entry.model_copy(
                    update={
                        "path": twin.path,
                        "size": twin.size,
                        "mtime": twin.mtime,
                        "duplicate_of": None,
                    }
                )
                self.repo.delete("import_manifest", twin.path)
                self.repo.put("import_manifest", promoted)
            for e in self.repo.all("import_manifest"):
                updates: dict[str, Any] = {}
                if e.duplicate_of == entry.path and e.path != twin.path:
                    updates["duplicate_of"] = twin.path
                if e.superseded_by == entry.path:
                    updates["superseded_by"] = twin.path
                if e.supersedes_candidate == entry.path:
                    updates["supersedes_candidate"] = twin.path
                if updates:
                    self.repo.put("import_manifest", e.model_copy(update=updates))
            self.repo.delete("import_manifest", entry.path)

    # ------------------------------------------------------------------ user actions

    def approve_supersession(self, path: str) -> ManifestEntry:
        """R3.11: B replaces A. Kept lines keep confirmation; strong fuzzy matches too."""
        b = self._entry(path)
        if not b.supersedes_candidate:
            raise ValueError("file is not a replacement candidate")
        a = self._entry(b.supersedes_candidate)
        a_lines = self._lines_of(a.sha256)
        b_staged = [t for t in self.repo.all("staging") if t.source.sha256 == b.sha256]
        a_fps: set[str] = {t.fingerprint for t in a_lines if t.fingerprint}
        b_fps: set[str] = {t.fingerprint for t in b_staged if t.fingerprint}
        kept = a_fps & b_fps
        auto_confirm: list[str] = []
        with self.repo.batch():
            for tx in b_staged:
                if tx.fingerprint in kept:
                    self.repo.delete("staging", tx.id)
            move_lines(self.repo, a.sha256, b, kept)
            # fuzzy carry-over for open (CSV) -> closed (PDF) invoices
            removed_a = [t for t in a_lines if t.fingerprint not in kept and t.review is None]
            for tx in [t for t in b_staged if t.fingerprint not in kept]:
                match = next(
                    (
                        r
                        for r in removed_a
                        if r.amount == tx.amount
                        and abs((r.purchase_date - tx.purchase_date).days) <= 2
                        and similarity(r.description, tx.description) >= 0.5
                    ),
                    None,
                )
                if match is None:
                    continue
                removed_a.remove(match)
                carried = self._carry_line(match, tx)
                self.repo.put("staging", carried)
                auto_confirm.append(carried.id)
            remove_lines(self.repo, a_fps - kept, self.clock.now(), sha=a.sha256)
            for coll in ("staging", "transactions"):
                for tx in self.repo.all(coll):
                    if tx.source.sha256 == a.sha256:
                        self.repo.delete(coll, tx.id)
            self.repo.put(
                "import_manifest",
                a.model_copy(update={"status": "superseded", "superseded_by": b.path}),
            )
            self.repo.put(
                "import_manifest",
                b.model_copy(update={"supersedes_candidate": None, "supersedes": a.path}),
            )
            refresh_status(self.repo, b.sha256)
        if auto_confirm:
            ok = [i for i in auto_confirm if self._confirmable(i)]
            if ok:
                Confirmer(self.repo, self.clock.now()).confirm(ok)
        return self._entry(path)

    def _carry_line(self, old: Transaction, new: Transaction) -> Transaction:
        """Approximate carry-over (open CSV -> closed PDF): the new line inherits my edits AND the
        links of the old one; derived objects are re-bound to the new fingerprint so the removal
        cascade of the old line does not orphan or duplicate them (review finding P1-2)."""
        assert old.fingerprint and new.fingerprint and new.review is not None
        installment = new.installment
        if old.installment and old.installment.plan_id and new.installment:
            installment = new.installment.model_copy(update={"plan_id": old.installment.plan_id})
        for plan in self.repo.all("installment_plans"):
            update: dict[str, Any] = {}
            if plan.origin.fingerprint == old.fingerprint:
                update["origin"] = plan.origin.model_copy(update={"fingerprint": new.fingerprint})
            ant = plan.anticipation
            if ant and old.fingerprint in ant.linked_fingerprints:
                update["anticipation"] = ant.model_copy(
                    update={
                        "linked_fingerprints": [
                            new.fingerprint if f == old.fingerprint else f
                            for f in ant.linked_fingerprints
                        ]
                    }
                )
            if update:
                self.repo.put("installment_plans", plan.model_copy(update=update))
        for st in self.repo.all("settlements"):
            if st.origin.fingerprint == old.fingerprint:
                self.repo.put(
                    "settlements",
                    st.model_copy(
                        update={
                            "origin": st.origin.model_copy(update={"fingerprint": new.fingerprint})
                        }
                    ),
                )
        for inv in self.repo.all("investments"):
            if any(m.origin.fingerprint == old.fingerprint for m in inv.movements):
                self.repo.put(
                    "investments",
                    inv.model_copy(
                        update={
                            "movements": [
                                m.model_copy(
                                    update={
                                        "origin": m.origin.model_copy(
                                            update={"fingerprint": new.fingerprint}
                                        )
                                    }
                                )
                                if m.origin.fingerprint == old.fingerprint
                                else m
                                for m in inv.movements
                            ]
                        }
                    ),
                )
        return new.model_copy(
            update={
                "category_id": old.category_id or new.category_id,
                "allocations": old.allocations,
                "allocation_origin": old.allocation_origin,
                "note": old.note,
                "kind": old.kind,
                "installment": installment,
                "links": old.links,
                "review": new.review.model_copy(update={"suggestions": []}),
            }
        )

    def _confirmable(self, tx_id: str) -> bool:
        tx = self.repo.get("staging", tx_id)
        return (
            tx is not None
            and tx.category_id is not None
            and tx.review is not None
            and tx.review.status == "pending"
        )

    def reject_supersession(self, path: str) -> ManifestEntry:
        b = self._entry(path)
        if not b.supersedes_candidate:
            raise ValueError("file is not a replacement candidate")
        with self.repo.batch():
            for tx in self.repo.all("staging"):
                if tx.source.sha256 == b.sha256:
                    self.repo.delete("staging", tx.id)
            self.repo.put(
                "import_manifest",
                b.model_copy(
                    update={
                        "status": "superseded",
                        "superseded_by": b.supersedes_candidate,
                        "supersedes_candidate": None,
                    }
                ),
            )
        return self._entry(path)

    def choose_owner(
        self, path: str, card_id: str | None, account_id: str | None, invoice_month: str | None
    ) -> ManifestEntry:
        """R4.8: remember the card/account (and month) of a file and reprocess it."""
        entry = self._entry(path)
        self.repo.put(
            "card_choices",
            CardChoice(
                id=new_id("choice"),
                sha256=entry.sha256,
                profile_id=entry.profile_id,
                card_hint=entry.card_hint,
                card_id=card_id,
                account_id=account_id,
                invoice_month=invoice_month,
            ),
        )
        if entry.card_hint and entry.profile_id:
            self.repo.put(
                "card_choices",
                CardChoice(
                    id=new_id("choice"),
                    profile_id=entry.profile_id,
                    card_hint=entry.card_hint,
                    card_id=card_id,
                    account_id=account_id,
                ),
            )
        return self.reprocess(path)

    def reprocess(self, path: str) -> ManifestEntry:
        entry = self._entry(path)
        if entry.active:
            self._changed(entry, entry.sha256, entry.size, entry.mtime)
        else:
            self.repo.delete("import_manifest", path)
            self._new(path, entry.sha256, entry.size, entry.mtime, keep=entry)
        return self._entry(path)

    def reprocess_failed(
        self, kinds: tuple[str, ...] = ("unknown_profile", "error", "awaiting_card")
    ) -> list[str]:
        done = []
        for e in self.repo.all("import_manifest"):
            if e.status in kinds and (self.settings.inbox_dir / e.path).is_file():
                self.reprocess(e.path)
                done.append(e.path)
        return done

    def _entry(self, path: str) -> ManifestEntry:
        entry: ManifestEntry | None = self.repo.get("import_manifest", path)
        if entry is None:
            raise KeyError(path)
        return entry


def staged_review(tx: Transaction) -> ReviewInfo:
    return tx.review or ReviewInfo()
