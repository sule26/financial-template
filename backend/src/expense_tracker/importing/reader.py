"""Read a file (PDF with optional password, CSV), detect its profile and parse it, with a timeout.

Parsing runs in a child process so that a catastrophic regex or a malicious PDF can never block
the processing queue (docs/13 "Regex catastrófica", ``PARSE_TIMEOUT_SECONDS``).
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from expense_tracker.importing.parser import (
    ParseError,
    csv_header,
    detect_csv,
    detect_pdf,
    parse_csv,
    parse_text,
)
from expense_tracker.importing.result import ParseResult
from expense_tracker.profiles.loader import ProfileSet


class PasswordError(ParseError):
    """Encrypted PDF and no configured password opened it."""


@dataclass
class Outcome:
    status: str  # ok | unknown_profile | error
    result: ParseResult | None = None
    profile_id: str | None = None
    error: str | None = None
    text: list[str] = field(default_factory=list)


def _is_password_error(exc: BaseException) -> bool:
    """pdfplumber >= 0.11.5 wraps pdfminer errors; look through the whole cause chain."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = type(current).__name__
        if (
            name in ("PDFPasswordIncorrect", "PDFEncryptionError")
            or "password" in str(current).lower()
        ):
            return True
        for arg in getattr(current, "args", ()):
            if isinstance(arg, BaseException) and _is_password_error(arg):
                return True
        current = current.__cause__ or current.__context__
    return False


def extract_pdf_pages(path: Path, passwords: list[str]) -> list[str]:
    """Text per page (layout-aware). Tries no password, then each configured password."""
    import pdfplumber

    attempts: list[str | None] = [None, *passwords]
    last_exc: Exception | None = None
    for pwd in attempts:
        try:
            with pdfplumber.open(path, password=pwd or "") as pdf:
                return [page.extract_text() or "" for page in pdf.pages]
        except Exception as exc:
            if _is_password_error(exc):
                last_exc = exc
                continue
            raise ParseError(f"cannot read PDF: {type(exc).__name__}") from exc
    raise PasswordError("encrypted PDF: no configured password opened it") from last_exc


def _parse(
    path: Path,
    kind: str,
    profiles: ProfileSet,
    passwords: list[str],
    forced_profile: str | None,
    as_of: date | None,
) -> Outcome:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        data = path.read_bytes()
        header = csv_header(data)
        candidates = [
            p for p in profiles.profiles.values() if p.kind == kind and detect_csv(p, header)
        ]
        if forced_profile:
            candidates = [p for p in profiles.profiles.values() if p.id == forced_profile]
        if not candidates:
            return Outcome("unknown_profile")
        if len(candidates) > 1:
            ids = ", ".join(sorted(p.id for p in candidates))
            return Outcome("error", error=f"ambiguous profiles: {ids}")
        profile = candidates[0]
        return Outcome("ok", parse_csv(profile, data, path.name, as_of), profile.id)
    pages = extract_pdf_pages(path, passwords)
    text = "\n".join(pages)
    matches: list[Any] = [
        p for p in profiles.profiles.values() if p.kind == kind and detect_pdf(p, text)
    ]
    plugin_matches = [p for p in profiles.plugins.values() if p.kind == kind and p.detect(text)]
    if forced_profile:
        matches = [p for p in profiles.profiles.values() if p.id == forced_profile]
        plugin_matches = [p for p in profiles.plugins.values() if p.id == forced_profile]
    total = len(matches) + len(plugin_matches)
    if total == 0:
        return Outcome("unknown_profile", text=pages)
    if total > 1:
        ids = ", ".join(sorted([p.id for p in matches] + [p.id for p in plugin_matches]))
        return Outcome("error", error=f"ambiguous profiles: {ids}", text=pages)
    if plugin_matches:
        plugin = plugin_matches[0]
        result = plugin.parse(pages)
        if not isinstance(result, ParseResult):
            result = ParseResult.model_validate(result)
        return Outcome("ok", result, plugin.id, text=pages)
    profile = matches[0]
    return Outcome("ok", parse_text(profile, pages, path.name), profile.id, text=pages)


def parse_file_inline(
    path: Path,
    kind: str,
    profiles: ProfileSet,
    passwords: list[str],
    forced_profile: str | None = None,
    as_of: date | None = None,
) -> Outcome:
    """Parse in the current process (used by the child and by tests)."""
    try:
        return _parse(path, kind, profiles, passwords, forced_profile, as_of)
    except PasswordError as exc:
        return Outcome("error", error=f"senha inválida ou ausente: {exc}")
    except ParseError as exc:
        return Outcome("error", error=str(exc))
    except Exception as exc:  # plugins are user code; never crash the queue
        return Outcome("error", error=f"{type(exc).__name__}: {exc}")


def _child(conn: Any, args: tuple[Any, ...]) -> None:  # pragma: no cover - runs in child
    try:
        outcome = parse_file_inline(*args)
        conn.send(
            (
                "ok",
                outcome.status,
                outcome.result.model_dump(mode="json") if outcome.result else None,
                outcome.profile_id,
                outcome.error,
                outcome.text,
            )
        )
    except Exception as exc:
        conn.send(("crash", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


def parse_file(
    path: Path,
    kind: str,
    profiles: ProfileSet,
    passwords: list[str],
    timeout: float,
    forced_profile: str | None = None,
    as_of: date | None = None,
) -> Outcome:
    """Parse with a hard timeout (child process, fork)."""
    ctx = mp.get_context("fork")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_child,
        args=(child, (path, kind, profiles, passwords, forced_profile, as_of)),
        daemon=True,
    )
    proc.start()
    child.close()
    try:
        if not parent.poll(timeout):
            proc.kill()
            proc.join(1)
            return Outcome("error", error=f"timeout: parse took more than {timeout:g}s")
        message = parent.recv()
    except EOFError:
        return Outcome("error", error="parser process died")
    finally:
        parent.close()
        proc.join(1)
    if message[0] == "crash":
        return Outcome("error", error=message[1])
    _, status, result, profile_id, error, text = message
    return Outcome(
        status, ParseResult.model_validate(result) if result else None, profile_id, error, text
    )
