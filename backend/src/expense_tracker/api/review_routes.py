"""Routes for review, sync/status and bank profiles (docs/05, 06, 09)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from expense_tracker.api.deps import AppContext, ctx
from expense_tracker.domain.documents import STATUS_LABELS
from expense_tracker.domain.models import Allocation, Kind
from expense_tracker.domain.months import Month
from expense_tracker.importing import parse_file
from expense_tracker.profiles import load_profiles, parse_profile
from expense_tracker.review.actions import edit_staged
from expense_tracker.review.confirm import Confirmer, ReviewError
from expense_tracker.services.errors import Conflict, Invalid, NotFound
from expense_tracker.sync import SyncService

router = APIRouter(prefix="/api")


def _sync(c: AppContext) -> SyncService:
    service: SyncService | None = c.extras.get("sync")
    if service is None:
        raise Conflict("sync_unavailable", "sync service not running")
    return service


def _review_error(exc: ReviewError) -> Invalid:
    return Invalid(exc.code, str(exc))


# ---------------------------------------------------------------- review


@router.get("/review", tags=["review"])
def review_files(c: AppContext = Depends(ctx)) -> list[dict[str, Any]]:
    staged = c.repo.all("staging")
    out = []
    for e in sorted(c.repo.all("import_manifest"), key=lambda e: e.path):
        lines = [t for t in staged if t.source.sha256 == e.sha256]
        if not lines and e.status != "pending_review":
            continue
        out.append(
            {
                "file": e.model_dump(mode="json"),
                "label": STATUS_LABELS[e.status],
                "count": len(lines),
                "lines": [
                    t.model_dump(mode="json")
                    for t in sorted(lines, key=lambda t: t.source.line or 0)
                ],
            }
        )
    return out


class StagedPatch(BaseModel):
    model_config = {"extra": "forbid"}

    category_id: str | None = None
    allocations: Allocation | None = None
    kind: Kind | None = None
    note: str | None = None
    choose: dict[str, str] | None = None
    reject: str | None = None
    accept: str | None = None


@router.patch("/review/lines/{tx_id}", tags=["review"])
def patch_line(tx_id: str, body: StagedPatch, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "allocations" in changes:
        changes["allocations"] = body.allocations
        c.catalog.check_allocation(body.allocations)
    try:
        return edit_staged(c.repo, tx_id, changes, c.clock.now())
    except ReviewError as exc:
        raise _review_error(exc) from exc


class ConfirmBody(BaseModel):
    ids: list[str] | None = None
    path: str | None = None


@router.post("/review/confirm", tags=["review"])
def confirm(body: ConfirmBody, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    ids = list(body.ids or [])
    if body.path:
        entry = c.repo.get("import_manifest", body.path)
        if entry is None:
            raise NotFound("not_found", f"file {body.path} not found")
        ids += [
            t.id
            for t in c.repo.all("staging")
            if t.source.sha256 == entry.sha256
            and (t.review is None or t.review.status != "overlap")
        ]
    if not ids:
        raise Invalid("nothing_to_confirm", "give ids or a file path")
    try:
        return Confirmer(c.repo, c.clock.now()).confirm(ids)
    except ReviewError as exc:
        raise _review_error(exc) from exc


# ---------------------------------------------------------------- sync / status


@router.get("/sync/status", tags=["sync"])
def sync_status(c: AppContext = Depends(ctx)) -> dict[str, Any]:
    service: SyncService | None = c.extras.get("sync")
    engine = service.engine if service else None
    files = []
    for e in sorted(c.repo.all("import_manifest"), key=lambda e: e.path):
        item = e.model_dump(mode="json")
        item["label"] = STATUS_LABELS[e.status]
        files.append(item)
    return {
        "files": files,
        "last_scan": engine.last_scan.isoformat() if engine and engine.last_scan else None,
        "last_report": engine.last_report.as_dict() if engine and engine.last_report else None,
        "jobs": [j.as_dict() for j in list(service.jobs.values())[-20:]] if service else [],
    }


@router.post("/sync/scan", status_code=202, tags=["sync"])
def sync_scan(c: AppContext = Depends(ctx)) -> dict[str, Any]:
    return _sync(c).scan().as_dict()


@router.get("/sync/jobs/{job_id}", tags=["sync"])
def sync_job(job_id: str, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    job = _sync(c).jobs.get(job_id)
    if job is None:
        raise NotFound("not_found", f"job {job_id} not found")
    return job.as_dict()


class FileAction(BaseModel):
    path: str


class OwnerChoice(BaseModel):
    path: str
    card_id: str | None = None
    account_id: str | None = None
    invoice_month: Month | None = None


def _safe_path(c: AppContext, rel: str) -> str:
    """docs/13 "Path traversal": paths from the API must stay inside the inbox."""
    root = c.settings.inbox_dir.resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root) or ".." in Path(rel).parts:
        raise Invalid("invalid_path", "path must be inside the inbox")
    return rel


def _run(c: AppContext, kind: str, fn: Any) -> dict[str, Any]:
    job = _sync(c).run_now(kind, fn)
    if job.status == "error":
        if job.error and job.error.startswith("KeyError"):
            raise NotFound("not_found", "file not found")
        raise Invalid("sync_error", job.error or "error")
    return job.as_dict()


@router.post("/sync/supersede/approve", tags=["sync"])
def approve(body: FileAction, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    path = _safe_path(c, body.path)
    return _run(c, "approve_supersession", lambda: _sync(c).engine.approve_supersession(path))


@router.post("/sync/supersede/reject", tags=["sync"])
def reject(body: FileAction, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    path = _safe_path(c, body.path)
    return _run(c, "reject_supersession", lambda: _sync(c).engine.reject_supersession(path))


@router.post("/sync/choose-owner", tags=["sync"])
def choose_owner(body: OwnerChoice, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    path = _safe_path(c, body.path)
    if not body.card_id and not body.account_id:
        raise Invalid("owner_required", "card_id or account_id is required")
    c.catalog._need("cards", body.card_id, "card_id")
    c.catalog._need("accounts", body.account_id, "account_id")
    return _run(
        c,
        "choose_owner",
        lambda: _sync(c).engine.choose_owner(
            path, body.card_id, body.account_id, body.invoice_month
        ),
    )


@router.post("/sync/reprocess", tags=["sync"])
def reprocess(body: FileAction, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    path = _safe_path(c, body.path)
    return _run(c, "reprocess", lambda: _sync(c).engine.reprocess(path))


# ---------------------------------------------------------------- profiles (R4.3)

PROFILE_FILE = re.compile(r"^[a-z0-9-]+$")


@router.get("/profiles", tags=["profiles"])
def list_profiles(c: AppContext = Depends(ctx)) -> dict[str, Any]:
    ps = load_profiles(c.settings.profiles_dir)
    counts: dict[str, dict[str, int]] = {}
    for e in c.repo.all("import_manifest"):
        if e.profile_id:
            row = counts.setdefault(e.profile_id, {"files": 0, "errors": 0})
            row["files"] += 1
            row["errors"] += 1 if e.status == "error" else 0
    examples_dir = c.settings.examples_dir
    examples = sorted(p.stem for p in examples_dir.glob("*.yaml")) if examples_dir.is_dir() else []
    return {
        "profiles": [
            {
                "id": p.id,
                "name": p.name,
                "kind": p.kind,
                "format": p.format,
                "file": ps.sources.get(p.id),
                **counts.get(p.id, {"files": 0, "errors": 0}),
            }
            for p in ps.profiles.values()
        ],
        "plugins": [
            {"id": p.id, "kind": p.kind, "file": ps.sources.get(p.id)} for p in ps.plugins.values()
        ],
        "errors": ps.errors,
        "examples": examples,
    }


@router.get("/profiles/examples/{name}", tags=["profiles"])
def get_example(name: str, c: AppContext = Depends(ctx)) -> dict[str, str]:
    """Example profile shipped with the app (``profiles/examples``), to start a new profile."""
    if not PROFILE_FILE.match(name):
        raise Invalid("invalid_id", "example name must match [a-z0-9-]+")
    path = c.settings.examples_dir / f"{name}.yaml"
    if not path.is_file():
        raise NotFound("not_found", f"example {name} not found")
    return {"id": name, "yaml": path.read_text("utf-8")}


@router.get("/profiles/{profile_id}", tags=["profiles"])
def get_profile(profile_id: str, c: AppContext = Depends(ctx)) -> dict[str, str]:
    ps = load_profiles(c.settings.profiles_dir)
    source = ps.sources.get(profile_id)
    if source is None or source.startswith("plugins/"):
        raise NotFound("not_found", f"profile {profile_id} not found")
    return {"id": profile_id, "yaml": (c.settings.profiles_dir / source).read_text("utf-8")}


class ProfileBody(BaseModel):
    yaml: str


@router.post("/profiles/validate", tags=["profiles"])
def validate_profile(body: ProfileBody) -> dict[str, Any]:
    try:
        profile = parse_profile(body.yaml)
    except ValueError as exc:
        return {"valid": False, "error": str(exc)}
    return {"valid": True, "id": profile.id}


@router.put("/profiles/{profile_id}", tags=["profiles"])
def save_profile(
    profile_id: str, body: ProfileBody, c: AppContext = Depends(ctx)
) -> dict[str, Any]:
    if not PROFILE_FILE.match(profile_id):
        raise Invalid("invalid_id", "profile id must match [a-z0-9-]+")
    try:
        profile = parse_profile(body.yaml)
    except ValueError as exc:
        raise Invalid("invalid_profile", str(exc)) from exc
    if profile.id != profile_id:
        raise Invalid("id_mismatch", "profile id in YAML differs from the URL")
    target = c.settings.profiles_dir / f"{profile_id}.yaml"
    target.write_text(body.yaml, encoding="utf-8")
    service: SyncService | None = c.extras.get("sync")
    job = service.submit("reprocess_failed", service.engine.reprocess_failed) if service else None
    return {"saved": profile_id, "job": job.as_dict() if job else None}


class ProfileTest(BaseModel):
    yaml: str
    path: str


@router.post("/profiles/test", tags=["profiles"])
def test_profile(body: ProfileTest, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    """Run a (possibly unsaved) profile against a file of the inbox (R4.3)."""
    path = _safe_path(c, body.path)
    file = c.settings.inbox_dir / path
    if not file.is_file():
        raise NotFound("not_found", "file not found in the inbox")
    try:
        profile = parse_profile(body.yaml)
    except ValueError as exc:
        return {"valid": False, "error": str(exc)}
    from expense_tracker.profiles.loader import ProfileSet

    ps = ProfileSet(profiles={profile.id: profile})
    from expense_tracker.sync.engine import SyncEngine

    passwords = SyncEngine(c.repo, c.settings, c.clock)._passwords()
    outcome = parse_file(
        file,
        profile.kind,
        ps,
        passwords,
        c.settings.parse_timeout_seconds,
        forced_profile=profile.id,
    )
    result = outcome.result
    return {
        "valid": True,
        "status": outcome.status,
        "error": outcome.error,
        "detected": outcome.status == "ok",
        "header": None
        if result is None
        else result.model_dump(mode="json", exclude={"lines", "ignored", "unrecognized"}),
        "lines": [] if result is None else [ln.model_dump(mode="json") for ln in result.lines],
        "ignored": [] if result is None else result.ignored,
        "unrecognized": [] if result is None else result.unrecognized,
    }


@router.post("/profiles/raw-text", tags=["profiles"])
def raw_text(body: FileAction, c: AppContext = Depends(ctx)) -> dict[str, Any]:
    """Extracted text of a PDF (to write regexes). Never logged."""
    path = _safe_path(c, body.path)
    file = c.settings.inbox_dir / path
    if not file.is_file():
        raise NotFound("not_found", "file not found in the inbox")
    if file.suffix.lower() == ".csv":
        return {"pages": [file.read_bytes().decode("utf-8", errors="replace")]}
    from expense_tracker.importing.reader import PasswordError, extract_pdf_pages
    from expense_tracker.sync.engine import SyncEngine

    try:
        pages = extract_pdf_pages(file, SyncEngine(c.repo, c.settings, c.clock)._passwords())
    except PasswordError as exc:
        raise Invalid("password", str(exc)) from exc
    return {"pages": pages}
