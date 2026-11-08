"""JSON repository (docs/04 "Regras gerais", design.md Decisão 1).

- One file per collection: ``{"schema_version": N, "items": [...]}``.
- Everything is loaded in memory at start; every mutation rewrites the whole file atomically
  (``tmp`` -> ``fsync`` -> ``os.replace`` -> ``fsync(dir)``).
- A process-wide ``fcntl`` lock on ``data/.lock`` prevents a second instance.
- ``batch()`` groups mutations; files are written on exit, ``import_manifest`` always last.
- Floats are rejected on write (invariant 4).
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import threading
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from expense_tracker.domain.documents import CardChoice, ManifestEntry
from expense_tracker.domain.models import (
    Account,
    Annotation,
    Benefit,
    Card,
    Category,
    InstallmentPlan,
    Institution,
    Investment,
    RecurringPurchase,
    Rule,
    SavingsGoal,
    Settlement,
    SplitProfile,
    Subscription,
    Transaction,
    User,
)

T = TypeVar("T", bound=BaseModel)

SCHEMA_VERSION = 1


class StorageError(RuntimeError):
    """Storage failure (corrupted file, lock held, invalid data)."""


class LockHeldError(StorageError):
    """Another instance holds the data directory lock."""


# collection name -> (model, key attribute)
COLLECTIONS: dict[str, tuple[type[BaseModel], str]] = {
    "users": (User, "id"),
    "split_profiles": (SplitProfile, "id"),
    "accounts": (Account, "id"),
    "cards": (Card, "id"),
    "categories": (Category, "id"),
    "savings_goals": (SavingsGoal, "id"),
    "transactions": (Transaction, "id"),
    "staging": (Transaction, "id"),
    "installment_plans": (InstallmentPlan, "id"),
    "subscriptions": (Subscription, "id"),
    "recurring_purchases": (RecurringPurchase, "id"),
    "rules": (Rule, "id"),
    "settlements": (Settlement, "id"),
    "annotations": (Annotation, "fingerprint"),
    "card_choices": (CardChoice, "id"),
    "investments": (Investment, "id"),
    "benefits": (Benefit, "id"),
    "institutions": (Institution, "id"),
    "import_manifest": (ManifestEntry, "path"),
}

WRITE_LAST = "import_manifest"

# name -> {from_version: migrate(items) -> items}
Migration = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
MIGRATIONS: dict[str, dict[int, Migration]] = {}


def _reject_floats(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        raise StorageError(f"float value at {path}; money must be a decimal string")
    if isinstance(value, dict):
        for k, v in value.items():
            _reject_floats(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _reject_floats(v, f"{path}[{i}]")


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON atomically; the old file stays intact if anything fails before replace."""
    _reject_floats(payload)
    tmp = path.with_name(f".{path.name}.tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


class Collection(Generic[T]):
    """In-memory ordered collection keyed by one attribute."""

    def __init__(self, name: str, model: type[T], key: str, items: list[T]) -> None:
        self.name = name
        self.model = model
        self.key = key
        self._items: dict[str, T] = {}
        for item in items:
            self._items[str(getattr(item, key))] = item

    def all(self) -> list[T]:
        return [item.model_copy(deep=True) for item in self._items.values()]

    def get(self, key: str) -> T | None:
        item = self._items.get(key)
        return item.model_copy(deep=True) if item is not None else None

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def keys(self) -> list[str]:
        return list(self._items)

    def _validated(self, item: T) -> T:
        payload = item.model_dump(mode="json")
        _reject_floats(payload)
        return self.model.model_validate(payload)

    def _put(self, item: T) -> None:
        validated = self._validated(item)
        self._items[str(getattr(validated, self.key))] = validated

    def _delete(self, key: str) -> bool:
        return self._items.pop(key, None) is not None

    def _replace(self, items: list[T]) -> None:
        validated = [self._validated(i) for i in items]  # validate all before touching state
        self._items = {str(getattr(v, self.key)): v for v in validated}

    def _snapshot(self) -> dict[str, T]:
        return dict(self._items)

    def _restore(self, snapshot: dict[str, T]) -> None:
        self._items = snapshot

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "items": [i.model_dump(mode="json") for i in self._items.values()],
        }


class Repository:
    """Single entry point to persisted data. Thread-safe for one process."""

    def __init__(self, data_dir: Path, backups_keep: int = 20) -> None:
        self.data_dir = data_dir
        self.backups_keep = backups_keep
        self._lock_fh: Any = None
        self._mutex = threading.RLock()
        self._dirty: set[str] = set()
        self._batch_depth = 0
        self._collections: dict[str, Collection[Any]] = {}

    # ---------------------------------------------------------- lifecycle

    def open(self) -> Repository:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._acquire_lock()
        self._migration_backup_done = False
        try:
            for name in COLLECTIONS:
                self._collections[name] = self._load(name)
        except Exception:
            self.close()
            raise
        return self

    def close(self) -> None:
        if self._lock_fh is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self._lock_fh, fcntl.LOCK_UN)
            self._lock_fh.close()
            self._lock_fh = None

    def __enter__(self) -> Repository:
        return self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _acquire_lock(self) -> None:
        fh = open(self.data_dir / ".lock", "a+")  # noqa: SIM115 - held for process lifetime
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            fh.close()
            raise LockHeldError(f"lock held: another instance is using {self.data_dir}") from exc
        self._lock_fh = fh

    # ---------------------------------------------------------- load / migrate

    def path(self, name: str) -> Path:
        return self.data_dir / f"{name}.json"

    def _load(self, name: str) -> Collection[Any]:
        model, key = COLLECTIONS[name]
        path = self.path(name)
        if not path.exists():
            return Collection(name, model, key, [])
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StorageError(f"{path.name} is not valid JSON: {exc}") from exc
        if not isinstance(raw, dict) or "items" not in raw:
            raise StorageError(f"{path.name}: missing envelope {{schema_version, items}}")
        try:
            version = int(raw.get("schema_version", 0))
        except (TypeError, ValueError) as exc:
            raise StorageError(f"{path.name}: schema_version must be an integer") from exc
        items = raw["items"]
        if not isinstance(items, list):
            raise StorageError(f"{path.name}: items must be a list")
        if version > SCHEMA_VERSION:
            raise StorageError(f"{path.name}: schema_version {version} is newer than supported")
        if version < SCHEMA_VERSION:
            if not self._migration_backup_done:
                self.backup(reason="migrate")
                self._migration_backup_done = True
            for v in range(version, SCHEMA_VERSION):
                migrate = MIGRATIONS.get(name, {}).get(v)
                if migrate is not None:
                    items = migrate(items)
        try:
            parsed = [model.model_validate(i) for i in items]
        except ValidationError as exc:
            raise StorageError(f"{path.name}: invalid data: {exc}") from exc
        collection = Collection(name, model, key, parsed)
        if version < SCHEMA_VERSION:
            atomic_write_json(path, collection.dump())
        return collection

    # ---------------------------------------------------------- access

    def col(self, name: str) -> Collection[Any]:
        return self._collections[name]

    def all(self, name: str) -> list[Any]:
        with self._mutex:
            return self._collections[name].all()

    def get(self, name: str, key: str | None) -> Any | None:
        if key is None:
            return None
        with self._mutex:
            return self._collections[name].get(key)

    def put(self, name: str, item: BaseModel) -> None:
        with self._mutex:
            try:
                self._collections[name]._put(item)
            except (ValidationError, StorageError) as exc:
                raise StorageError(f"{name}: invalid item: {exc}") from exc
            self._mark(name)

    def delete(self, name: str, key: str) -> bool:
        with self._mutex:
            removed = self._collections[name]._delete(key)
            if removed:
                self._mark(name)
            return removed

    def replace_all(self, name: str, items: list[Any]) -> None:
        with self._mutex:
            try:
                self._collections[name]._replace(items)
            except (ValidationError, StorageError) as exc:
                raise StorageError(f"{name}: invalid item: {exc}") from exc
            self._mark(name)

    # ---------------------------------------------------------- writes

    def _mark(self, name: str) -> None:
        self._dirty.add(name)
        if self._batch_depth == 0:
            self.flush()

    @contextlib.contextmanager
    def batch(self) -> Iterator[Repository]:
        """Group mutations; flush once on success (manifest written last).

        On exception every collection is restored to its state at the start of the outermost
        batch and nothing is written (no half-applied operation survives in memory).
        """
        with self._mutex:
            outer = self._batch_depth == 0
            snapshot = {n: c._snapshot() for n, c in self._collections.items()} if outer else {}
            dirty_before = set(self._dirty) if outer else set()
            self._batch_depth += 1
            try:
                yield self
            except BaseException:
                self._batch_depth -= 1
                if outer:
                    for n, items in snapshot.items():
                        self._collections[n]._restore(items)
                    self._dirty = dirty_before
                raise
            self._batch_depth -= 1
            if outer:
                self.flush()

    def flush(self) -> None:
        with self._mutex:
            names = sorted(self._dirty, key=lambda n: (n == WRITE_LAST, n))
            for name in names:
                atomic_write_json(self.path(name), self._collections[name].dump())
                self._dirty.discard(name)

    # ---------------------------------------------------------- backups

    def backup(self, reason: str = "auto") -> Path | None:
        """Copy every ``*.json`` to ``.backups/<timestamp>-<reason>/``; keep ``backups_keep``."""
        files = sorted(self.data_dir.glob("*.json"))
        if not files:
            return None
        root = self.data_dir / ".backups"
        root.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        target = root / f"{stamp}-{reason}"
        target.mkdir()
        for f in files:
            shutil.copy2(f, target / f.name)
        # manual backups (``task backup`` / reason "manual") are never rotated away
        existing = sorted(
            p for p in root.iterdir() if p.is_dir() and not p.name.endswith("-manual")
        )
        for old in existing[: max(0, len(existing) - self.backups_keep)]:
            shutil.rmtree(old, ignore_errors=True)
        return target
