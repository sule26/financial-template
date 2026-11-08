"""Tests for the JSON repository (docs/04 "Regras gerais" / "Invariantes", docs/11 "storage").

Requirements covered: R2.1 (configurable data dir), R2.2 (atomic writes), R2.3 (schema_version and
migrations with backup), R2.4 (money as decimal strings, never floats).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from expense_tracker.config import Settings
from expense_tracker.domain.documents import CardChoice, ManifestEntry
from expense_tracker.domain.models import (
    Account,
    Annotation,
    Anticipation,
    Benefit,
    BillingEntry,
    Card,
    Category,
    IncomeEntry,
    InstallmentPlan,
    InstallmentRef,
    Institution,
    Interval,
    Investment,
    Movement,
    RecurringPurchase,
    ReviewInfo,
    Rule,
    RuleThen,
    RuleWhen,
    SavingsGoal,
    Settlement,
    Share,
    Snapshot,
    Source,
    SplitProfile,
    SplitRef,
    SplitVersion,
    Subscription,
    Suggestion,
    Transaction,
    User,
)
from expense_tracker.storage import (
    COLLECTIONS,
    LockHeldError,
    Repository,
    StorageError,
    atomic_write_json,
)
from expense_tracker.storage import repository as repo_module

# ---------------------------------------------------------------- builders

ME = [Share(user_id="usr_eu", pct=Decimal("100.00"))]


def make_user(user_id: str = "usr_eu", name: str = "Eu") -> User:
    return User(
        id=user_id,
        name=name,
        aliases=["EU"],
        income_history=[IncomeEntry(from_month="2026-01", amount=Decimal("5000"))],
    )


def make_transaction(tx_id: str = "tx_1", **overrides: Any) -> Transaction:
    data: dict[str, Any] = {
        "id": tx_id,
        "fingerprint": f"fp_{tx_id}",
        "source": Source(type="manual"),
        "card_id": "card_inter",
        "purchase_date": date(2026, 9, 14),
        "invoice_month": "2026-10",
        "description": "MERCADO",
        "amount": Decimal("150.00"),
        "installment": InstallmentRef(n=1, of=3),
        "allocations": [
            Share(user_id="usr_eu", pct=Decimal("60.00")),
            Share(user_id="usr_ana", pct=Decimal("40.00")),
        ],
    }
    data.update(overrides)
    return Transaction(**data)


def make_manifest_entry(path: str = "faturas/inter-2026-10.pdf") -> ManifestEntry:
    return ManifestEntry(
        path=path,
        sha256="a" * 64,
        size=1234,
        mtime=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        kind="fatura",
        card_id="card_inter",
        invoice_month="2026-10",
        total=Decimal("150.00"),
        tx_fingerprints=["fp_tx_1"],
    )


# One representative item per collection; must cover every name in COLLECTIONS.
SAMPLES: dict[str, Callable[[], BaseModel]] = {
    "users": make_user,
    "split_profiles": lambda: SplitProfile(
        id="split_casal",
        name="Casal",
        members=["usr_eu", "usr_ana"],
        history=[
            SplitVersion(
                from_month="2026-01",
                shares=[
                    Share(user_id="usr_eu", pct=Decimal("60.00")),
                    Share(user_id="usr_ana", pct=Decimal("40.00")),
                ],
            )
        ],
    ),
    "accounts": lambda: Account(
        id="acc_inter", name="Conta Inter", owners=ME, responsible_user_id="usr_eu"
    ),
    "cards": lambda: Card(
        id="card_inter",
        name="Inter",
        owners=SplitRef(split_id="split_casal"),
        responsible_user_id="usr_eu",
        last_digits=["1234"],
        billing_history=[BillingEntry(from_month="2026-01", closing_day=5, due_day=12)],
        limit=Decimal("10000"),
    ),
    "categories": lambda: Category(id="cat_food", name="Mercado", budget=Decimal("800")),
    "savings_goals": lambda: SavingsGoal(
        id="goal_trip", name="Viagem", monthly_amount=Decimal("300.00")
    ),
    "transactions": make_transaction,
    "staging": lambda: make_transaction(
        "tx_stg", source=Source(type="import", sha256="a" * 64, path="faturas/x.pdf", line=3)
    ),
    "installment_plans": lambda: InstallmentPlan(
        id="plan_tv",
        card_id="card_inter",
        description="TV",
        total_installments=10,
        first_invoice_month="2026-10",
        total_amount=Decimal("1000.00"),
        anticipation=Anticipation(from_n=8, target_month="2027-03"),
    ),
    "subscriptions": lambda: Subscription(
        id="sub_stream",
        description="Streaming",
        amount=Decimal("39.90"),
        card_id="card_inter",
        start_month="2026-01",
    ),
    "recurring_purchases": lambda: RecurringPurchase(
        id="rec_food",
        description="Ração",
        estimated_amount=Decimal("180.00"),
        every=Interval(value=45),
        last_date=date(2026, 9, 1),
        card_id="card_inter",
    ),
    "rules": lambda: Rule(
        id="rule_market",
        when=RuleWhen(description_regex="MERCADO", min_amount=Decimal("1.00")),
        then=RuleThen(category_id="cat_food"),
    ),
    "settlements": lambda: Settlement(
        id="set_1",
        from_user_id="usr_ana",
        to_user_id="usr_eu",
        amount=Decimal("250.00"),
        date=date(2026, 10, 5),
        month="2026-10",
    ),
    "annotations": lambda: Annotation(
        fingerprint="fp_tx_1", note="presente", amount=Decimal("10.00")
    ),
    "card_choices": lambda: CardChoice(
        id="cc_1", sha256="a" * 64, card_id="card_inter", invoice_month="2026-10"
    ),
    "benefits": lambda: Benefit(
        id="ben_vr",
        name="VR",
        user_id="usr_eu",
        destination="card",
        account_id="acc_vr",
        amount_history=[IncomeEntry(from_month="2026-01", amount="800.00")],
    ),
    "investments": lambda: Investment(
        id="inv_reserve",
        name="Reserva",
        owners=ME,
        snapshots=[Snapshot(date=date(2026, 9, 30), balance=Decimal("1000.00"))],
        movements=[Movement(date=date(2026, 9, 1), type="contribution", amount=Decimal("100.00"))],
    ),
    "institutions": lambda: Institution(id="inst_xp", name="XP", type="broker"),
    "import_manifest": make_manifest_entry,
}


def _key(name: str, item: BaseModel) -> str:
    return str(getattr(item, COLLECTIONS[name][1]))


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _no_float(value: str) -> Any:
    raise AssertionError(f"float found on disk: {value}")


def _write_raw(data_dir: Path, name: str, payload: Any) -> Path:
    path = data_dir / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def repo(data_dir: Path) -> Iterator[Repository]:
    r = Repository(data_dir).open()
    yield r
    r.close()


@pytest.fixture
def write_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the collection name of every atomic write, delegating to the real function."""
    calls: list[str] = []
    real = repo_module.atomic_write_json

    def spy(path: Path, payload: Any) -> None:
        calls.append(path.stem)
        real(path, payload)

    monkeypatch.setattr(repo_module, "atomic_write_json", spy)
    return calls


# ---------------------------------------------------------------- round trip and envelope


def test_samples_cover_every_collection() -> None:
    assert set(SAMPLES) == set(COLLECTIONS)


@pytest.mark.parametrize("name", sorted(COLLECTIONS))
def test_r2_1_round_trip_each_collection(data_dir: Path, name: str) -> None:
    item = SAMPLES[name]()
    with Repository(data_dir) as repo:
        repo.put(name, item)

    with Repository(data_dir) as reopened:
        assert reopened.all(name) == [item]
        assert reopened.get(name, _key(name, item)) == item


@pytest.mark.parametrize("name", sorted(COLLECTIONS))
def test_r2_3_file_has_envelope_with_schema_version(repo: Repository, name: str) -> None:
    item = SAMPLES[name]()
    repo.put(name, item)

    raw = _read(repo.path(name))

    assert set(raw) == {"schema_version", "items"}
    assert raw["schema_version"] == repo_module.SCHEMA_VERSION
    assert raw["items"] == [item.model_dump(mode="json")]


def test_r2_1_missing_files_open_as_empty_collections(repo: Repository) -> None:
    for name in COLLECTIONS:
        assert repo.all(name) == []
    assert list(repo.data_dir.glob("*.json")) == []


def test_r2_1_data_dir_is_configurable_and_created(tmp_path: Path) -> None:
    data_dir = tmp_path / "custom" / "nested" / "data"

    with Repository(data_dir) as repo:
        repo.put("users", make_user())

    assert (data_dir / "users.json").is_file()
    assert {p.name for p in tmp_path.rglob("*.json")} == {"users.json"}


def test_r2_1_data_dir_from_settings_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "from-env"))
    settings = Settings.from_env()

    with Repository(settings.data_dir, backups_keep=settings.backups_keep) as repo:
        repo.put("users", make_user())

    assert (tmp_path / "from-env" / "users.json").is_file()


def test_r2_1_repository_uses_settings_fixture_dir(settings: Settings) -> None:
    with Repository(settings.data_dir, backups_keep=settings.backups_keep) as repo:
        repo.put("categories", SAMPLES["categories"]())
        assert repo.backups_keep == 5

    assert (settings.data_dir / "categories.json").is_file()


def test_collection_accessors(repo: Repository) -> None:
    repo.put("users", make_user("usr_eu"))
    repo.put("users", make_user("usr_ana", "Ana"))

    col = repo.col("users")

    assert col.keys() == ["usr_eu", "usr_ana"]
    assert "usr_ana" in col
    assert "usr_x" not in col
    assert len(col) == 2


def test_put_same_key_replaces_item(repo: Repository) -> None:
    repo.put("users", make_user("usr_eu", "Eu"))
    repo.put("users", make_user("usr_eu", "Eu Mesmo"))

    assert [u.name for u in repo.all("users")] == ["Eu Mesmo"]
    assert len(_read(repo.path("users"))["items"]) == 1


def test_items_keep_insertion_order_after_reopen(data_dir: Path) -> None:
    ids = ["usr_c", "usr_a", "usr_b"]
    with Repository(data_dir) as repo:
        for user_id in ids:
            repo.put("users", make_user(user_id))

    with Repository(data_dir) as reopened:
        assert [u.id for u in reopened.all("users")] == ids


# ---------------------------------------------------------------- copies, delete, replace


def test_get_returns_copy(repo: Repository) -> None:
    repo.put("users", make_user())

    fetched = repo.get("users", "usr_eu")
    assert fetched is not None
    fetched.aliases.append("MUTATED")
    fetched.name = "Mutated"

    stored = repo.get("users", "usr_eu")
    assert stored is not None
    assert stored.aliases == ["EU"]
    assert stored.name == "Eu"


def test_all_returns_copies(repo: Repository) -> None:
    repo.put("users", make_user())

    listed = repo.all("users")
    listed[0].income_history.clear()
    listed.clear()

    assert len(repo.all("users")) == 1
    assert len(repo.all("users")[0].income_history) == 1


def test_put_stores_copy_of_argument(repo: Repository) -> None:
    user = make_user()
    repo.put("users", user)

    user.aliases.append("MUTATED")

    stored = repo.get("users", "usr_eu")
    assert stored is not None
    assert stored.aliases == ["EU"]


def test_get_missing_returns_none(repo: Repository) -> None:
    assert repo.get("users", "usr_missing") is None


def test_delete_missing_returns_false_and_does_not_write(
    repo: Repository, write_spy: list[str]
) -> None:
    assert repo.delete("users", "usr_missing") is False
    assert write_spy == []


def test_delete_existing_returns_true_and_persists(data_dir: Path) -> None:
    with Repository(data_dir) as repo:
        repo.put("users", make_user("usr_eu"))
        repo.put("users", make_user("usr_ana", "Ana"))
        assert repo.delete("users", "usr_eu") is True

    with Repository(data_dir) as reopened:
        assert [u.id for u in reopened.all("users")] == ["usr_ana"]


def test_replace_all_persists_new_items(data_dir: Path) -> None:
    with Repository(data_dir) as repo:
        repo.put("users", make_user("usr_old"))
        repo.replace_all("users", [make_user("usr_a"), make_user("usr_b")])

    with Repository(data_dir) as reopened:
        assert [u.id for u in reopened.all("users")] == ["usr_a", "usr_b"]


# ---------------------------------------------------------------- invalid items


def test_put_invalid_item_raises_storage_error(repo: Repository) -> None:
    invalid = User.model_construct(id="usr_bad", name="")  # bypasses validation

    with pytest.raises(StorageError, match="users: invalid item"):
        repo.put("users", invalid)

    assert repo.get("users", "usr_bad") is None
    assert not repo.path("users").exists()


def test_put_item_of_wrong_model_raises_storage_error(repo: Repository) -> None:
    with pytest.raises(StorageError):
        repo.put("users", SAMPLES["categories"]())

    assert repo.all("users") == []


def test_replace_all_invalid_item_raises_storage_error_and_keeps_items(repo: Repository) -> None:
    repo.put("users", make_user("usr_keep"))
    invalid = User.model_construct(id="usr_bad", name="")

    with pytest.raises(StorageError):
        repo.replace_all("users", [make_user("usr_a"), invalid])

    assert [u.id for u in repo.all("users")] == ["usr_keep"]


def test_invalid_item_on_disk_raises_storage_error(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    _write_raw(data_dir, "users", {"schema_version": 1, "items": [{"id": "usr_x", "name": ""}]})

    with pytest.raises(StorageError, match="invalid data"):
        Repository(data_dir).open()


# ---------------------------------------------------------------- corrupted files


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "not valid JSON"),
        ("", "not valid JSON"),
        ("[]", "missing envelope"),
        ('{"schema_version": 1}', "missing envelope"),
        ('"just a string"', "missing envelope"),
    ],
    ids=["broken", "empty", "bare-list", "no-items", "scalar"],
)
def test_corrupted_file_raises_storage_error(data_dir: Path, content: str, message: str) -> None:
    data_dir.mkdir(parents=True)
    (data_dir / "transactions.json").write_text(content, encoding="utf-8")

    with pytest.raises(StorageError, match=message):
        Repository(data_dir).open()


def test_failed_open_releases_lock(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    path = data_dir / "users.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError):
        Repository(data_dir).open()

    path.write_text(json.dumps({"schema_version": 1, "items": []}), encoding="utf-8")

    with Repository(data_dir) as repo:
        assert repo.all("users") == []


def test_items_null_raises_storage_error(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    _write_raw(data_dir, "users", {"schema_version": 1, "items": None})

    with pytest.raises(StorageError):
        Repository(data_dir).open()


def test_r2_3_non_integer_schema_version_raises_storage_error(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    _write_raw(data_dir, "users", {"schema_version": "abc", "items": []})

    with pytest.raises(StorageError):
        Repository(data_dir).open()


# ---------------------------------------------------------------- R2.2 atomic writes / crash


def _boom(*_args: Any, **_kwargs: Any) -> None:
    raise OSError("simulated crash")


@pytest.mark.parametrize("failing", ["replace", "fsync"])
def test_r2_2_crash_keeps_previous_file(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    repo = Repository(data_dir).open()
    repo.put("users", make_user("usr_eu", "Original"))
    path = repo.path("users")
    before = path.read_bytes()

    monkeypatch.setattr(repo_module.os, failing, _boom)
    with pytest.raises(OSError, match="simulated crash"):
        repo.put("users", make_user("usr_eu", "Changed"))
    monkeypatch.undo()
    repo.close()

    assert path.read_bytes() == before
    assert _read(path)["items"][0]["name"] == "Original"
    with Repository(data_dir) as reopened:
        user = reopened.get("users", "usr_eu")
        assert user is not None
        assert user.name == "Original"


def test_r2_2_crash_before_replace_leaves_no_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "fresh.json"
    monkeypatch.setattr(repo_module.os, "replace", _boom)

    with pytest.raises(OSError):
        atomic_write_json(path, {"schema_version": 1, "items": []})

    assert not path.exists()


def test_r2_2_atomic_write_replaces_content_and_cleans_tmp(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    atomic_write_json(path, {"v": 1})
    atomic_write_json(path, {"v": 2, "text": "ação"})

    assert _read(path) == {"v": 2, "text": "ação"}
    assert "ação" in path.read_text(encoding="utf-8")  # ensure_ascii=False
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_r2_2_crash_in_data_write_keeps_manifest_untouched(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # docs/05#garantias-e-falhas: data first, manifest last; a crash midway must not
    # advance the manifest.
    repo = Repository(data_dir).open()
    repo.put("import_manifest", make_manifest_entry("faturas/old.pdf"))
    manifest_before = repo.path("import_manifest").read_bytes()
    real = repo_module.atomic_write_json

    def crash_on_transactions(path: Path, payload: Any) -> None:
        if path.stem == "transactions":
            raise OSError("simulated crash")
        real(path, payload)

    monkeypatch.setattr(repo_module, "atomic_write_json", crash_on_transactions)
    with pytest.raises(OSError), repo.batch():
        repo.put("import_manifest", make_manifest_entry("faturas/new.pdf"))
        repo.put("transactions", make_transaction())
    repo.close()

    assert repo.path("import_manifest").read_bytes() == manifest_before
    assert not repo.path("transactions").exists()


# ---------------------------------------------------------------- lock


def test_second_instance_raises_lock_held_error(repo: Repository) -> None:
    with pytest.raises(LockHeldError, match="another instance"):
        Repository(repo.data_dir).open()


def test_lock_held_error_is_storage_error() -> None:
    assert issubclass(LockHeldError, StorageError)


def test_lock_released_on_close(data_dir: Path) -> None:
    with Repository(data_dir):
        pass

    second = Repository(data_dir).open()
    second.close()
    second.close()  # closing twice is harmless


def test_failed_second_instance_does_not_break_first(repo: Repository) -> None:
    with pytest.raises(LockHeldError):
        Repository(repo.data_dir).open()

    repo.put("users", make_user())
    assert repo.get("users", "usr_eu") is not None
    with pytest.raises(LockHeldError):
        Repository(repo.data_dir).open()


# ---------------------------------------------------------------- R2.3 migrations


def _rename_full_name(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": i["id"], "name": i["full_name"]} for i in items]


def test_r2_3_old_schema_is_migrated_rewritten_and_backed_up(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir.mkdir(parents=True)
    original = {"schema_version": 0, "items": [{"id": "usr_ana", "full_name": "Ana"}]}
    path = _write_raw(data_dir, "users", original)
    monkeypatch.setitem(repo_module.MIGRATIONS, "users", {0: _rename_full_name})

    with Repository(data_dir) as repo:
        user = repo.get("users", "usr_ana")

    assert user is not None
    assert user.name == "Ana"
    rewritten = _read(path)
    assert rewritten["schema_version"] == repo_module.SCHEMA_VERSION
    assert rewritten["items"][0]["name"] == "Ana"
    backups = list((data_dir / ".backups").iterdir())
    assert len(backups) == 1
    assert backups[0].name.endswith("-migrate")
    assert _read(backups[0] / "users.json") == original


def test_r2_3_migrations_run_in_sequence(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir.mkdir(parents=True)
    _write_raw(data_dir, "categories", {"schema_version": 1, "items": [{"id": "cat_a"}]})
    order: list[int] = []

    def step(version: int, field: str, value: str) -> Callable[..., list[dict[str, Any]]]:
        def migrate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            order.append(version)
            return [{**i, field: value} for i in items]

        return migrate

    monkeypatch.setattr(repo_module, "SCHEMA_VERSION", 3)
    monkeypatch.setitem(
        repo_module.MIGRATIONS,
        "categories",
        {1: step(1, "name", "Mercado"), 2: step(2, "color", "#000000")},
    )

    with Repository(data_dir) as repo:
        cat = repo.get("categories", "cat_a")

    assert order == [1, 2]
    assert cat is not None
    assert (cat.name, cat.color) == ("Mercado", "#000000")
    assert _read(data_dir / "categories.json")["schema_version"] == 3


def test_r2_3_missing_schema_version_is_treated_as_oldest(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir.mkdir(parents=True)
    _write_raw(data_dir, "users", {"items": [{"id": "usr_ana", "full_name": "Ana"}]})
    monkeypatch.setitem(repo_module.MIGRATIONS, "users", {0: _rename_full_name})

    with Repository(data_dir) as repo:
        assert repo.get("users", "usr_ana") is not None

    assert _read(data_dir / "users.json")["schema_version"] == repo_module.SCHEMA_VERSION


def test_r2_3_old_schema_without_registered_migration_is_rewritten(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    item = make_user().model_dump(mode="json")
    _write_raw(data_dir, "users", {"schema_version": 0, "items": [item]})

    with Repository(data_dir) as repo:
        assert repo.get("users", "usr_eu") == make_user()

    assert _read(data_dir / "users.json") == {
        "schema_version": repo_module.SCHEMA_VERSION,
        "items": [item],
    }
    assert len(list((data_dir / ".backups").iterdir())) == 1


def test_r2_3_current_schema_is_not_rewritten_nor_backed_up(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    path = _write_raw(
        data_dir, "users", {"schema_version": 1, "items": [make_user().model_dump(mode="json")]}
    )
    before = path.read_bytes()

    with Repository(data_dir):
        pass

    assert path.read_bytes() == before
    assert not (data_dir / ".backups").exists()


def test_r2_3_newer_schema_raises_storage_error(data_dir: Path) -> None:
    data_dir.mkdir(parents=True)
    path = _write_raw(data_dir, "users", {"schema_version": 99, "items": []})
    before = path.read_bytes()

    with pytest.raises(StorageError, match="newer than supported"):
        Repository(data_dir).open()

    assert path.read_bytes() == before


# ---------------------------------------------------------------- R2.4 money / floats


def test_r2_4_atomic_write_rejects_float(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    atomic_write_json(path, {"items": []})
    before = path.read_bytes()

    with pytest.raises(StorageError, match=r"\$\.items\[0\]\.amount"):
        atomic_write_json(path, {"items": [{"amount": 1.5}]})

    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "payload", [1.0, [0.1], {"a": {"b": [1, 2.5]}}], ids=["scalar", "list", "nested"]
)
def test_r2_4_atomic_write_rejects_float_anywhere(tmp_path: Path, payload: Any) -> None:
    with pytest.raises(StorageError, match="float"):
        atomic_write_json(tmp_path / "x.json", payload)

    assert not (tmp_path / "x.json").exists()


def _float_transaction() -> Transaction:
    return make_transaction(
        "tx_float",
        review=ReviewInfo(suggestions=[Suggestion(type="category", data={"score": 0.9})]),
    )


def test_r2_4_item_with_float_is_rejected_on_write(repo: Repository) -> None:
    repo.put("transactions", make_transaction("tx_ok"))
    before = repo.path("transactions").read_bytes()

    with pytest.raises(StorageError, match="float"):
        repo.put("transactions", _float_transaction())

    assert repo.path("transactions").read_bytes() == before


def test_r2_4_rejected_float_item_does_not_poison_collection(repo: Repository) -> None:
    with pytest.raises(StorageError):
        repo.put("transactions", _float_transaction())

    assert repo.get("transactions", "tx_float") is None
    repo.put("transactions", make_transaction("tx_ok"))
    assert [i["id"] for i in _read(repo.path("transactions"))["items"]] == ["tx_ok"]


def test_r2_4_money_is_written_as_two_decimal_string(repo: Repository) -> None:
    repo.put("categories", Category(id="cat_food", name="Mercado", budget=Decimal("150")))
    repo.put("transactions", make_transaction(amount=Decimal("-65.5")))

    category = _read(repo.path("categories"))["items"][0]
    tx = _read(repo.path("transactions"))["items"][0]

    assert category["budget"] == "150.00"
    assert tx["amount"] == "-65.50"
    assert [a["pct"] for a in tx["allocations"]] == ["60.00", "40.00"]


@pytest.mark.parametrize("name", sorted(COLLECTIONS))
def test_r2_4_no_float_on_disk(repo: Repository, name: str) -> None:
    repo.put(name, SAMPLES[name]())

    json.loads(repo.path(name).read_text(encoding="utf-8"), parse_float=_no_float)


def test_r2_4_float_money_rejected_by_model() -> None:
    with pytest.raises(ValueError, match="float"):
        Category(id="cat_x", name="X", budget=1.5)


# ---------------------------------------------------------------- batch


def test_each_mutation_outside_batch_writes_immediately(
    repo: Repository, write_spy: list[str]
) -> None:
    repo.put("users", make_user("usr_a"))
    repo.put("users", make_user("usr_b"))

    assert write_spy == ["users", "users"]


def test_batch_writes_each_collection_once_with_manifest_last(
    repo: Repository, write_spy: list[str]
) -> None:
    # docs/04#regras-gerais: data first, import_manifest.json last.
    with repo.batch():
        repo.put("import_manifest", make_manifest_entry())
        repo.put("transactions", make_transaction("tx_1"))
        repo.put("transactions", make_transaction("tx_2"))
        repo.put("staging", SAMPLES["staging"]())
        repo.put("annotations", SAMPLES["annotations"]())
        assert write_spy == []

    assert sorted(write_spy) == sorted(
        ["import_manifest", "transactions", "staging", "annotations"]
    )
    assert write_spy[-1] == "import_manifest"
    assert len(_read(repo.path("transactions"))["items"]) == 2


def test_nested_batch_flushes_only_at_outermost(repo: Repository, write_spy: list[str]) -> None:
    with repo.batch():
        with repo.batch():
            repo.put("users", make_user())
        assert write_spy == []
        repo.put("import_manifest", make_manifest_entry())

    assert write_spy == ["users", "import_manifest"]


def test_batch_without_changes_writes_nothing(repo: Repository, write_spy: list[str]) -> None:
    with repo.batch() as same:
        assert same is repo

    assert write_spy == []


def test_batch_does_not_write_when_block_raises(repo: Repository, write_spy: list[str]) -> None:
    with pytest.raises(RuntimeError), repo.batch():
        repo.put("users", make_user())
        raise RuntimeError("abort")

    assert write_spy == []
    assert not repo.path("users").exists()


def test_batch_data_persisted_after_reopen(data_dir: Path) -> None:
    with Repository(data_dir) as repo, repo.batch():
        repo.put("transactions", make_transaction())
        repo.put("import_manifest", make_manifest_entry())

    with Repository(data_dir) as reopened:
        assert len(reopened.all("transactions")) == 1
        assert len(reopened.all("import_manifest")) == 1


# ---------------------------------------------------------------- backups


class _TickingDatetime:
    """Deterministic ``datetime.now()`` that advances one second per call."""

    current = datetime(2026, 10, 12, 10, 0, 0)

    @classmethod
    def now(cls) -> datetime:
        cls.current += timedelta(seconds=1)
        return cls.current


@pytest.fixture
def ticking_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    _TickingDatetime.current = datetime(2026, 10, 12, 10, 0, 0)
    monkeypatch.setattr(repo_module, "datetime", _TickingDatetime)


def test_backup_without_files_returns_none(repo: Repository) -> None:
    assert repo.backup() is None
    assert not (repo.data_dir / ".backups").exists()


def test_backup_copies_every_json_file(repo: Repository, ticking_clock: None) -> None:
    repo.put("users", make_user())
    repo.put("transactions", make_transaction())

    target = repo.backup(reason="import")

    assert target is not None
    assert target.parent == repo.data_dir / ".backups"
    assert target.name.endswith("-import")
    assert sorted(p.name for p in target.iterdir()) == ["transactions.json", "users.json"]
    assert (target / "users.json").read_bytes() == repo.path("users").read_bytes()


def test_backups_rotate_keeping_backups_keep(data_dir: Path, ticking_clock: None) -> None:
    with Repository(data_dir, backups_keep=3) as repo:
        repo.put("users", make_user())
        created = [repo.backup(reason=f"b{i}") for i in range(5)]

    remaining = sorted((data_dir / ".backups").iterdir())
    assert remaining == created[-3:]


def test_backup_rotation_ignores_stray_files(data_dir: Path, ticking_clock: None) -> None:
    with Repository(data_dir, backups_keep=1) as repo:
        repo.put("users", make_user())
        (data_dir / ".backups").mkdir()
        (data_dir / ".backups" / "README").write_text("keep me", encoding="utf-8")
        repo.backup()
        last = repo.backup()

    entries = sorted(p.name for p in (data_dir / ".backups").iterdir())
    assert last is not None
    assert entries == sorted(["README", last.name])


# ---------------------------------------------------------------- review regressions


def test_r2_2_failed_batch_rolls_back_memory_and_writes_nothing(
    repo: Repository, write_spy: list[str]
) -> None:
    repo.put("users", make_user("usr_keep"))
    write_spy.clear()
    with pytest.raises(RuntimeError, match="boom"), repo.batch():
        repo.put("users", make_user("usr_half"))
        repo.delete("users", "usr_keep")
        raise RuntimeError("boom")
    assert write_spy == []
    assert repo.get("users", "usr_half") is None
    assert repo.get("users", "usr_keep") is not None
    # a later unrelated write must not persist the aborted changes
    repo.put("categories", Category(id="cat_x", name="X"))
    assert [u["id"] for u in json.loads(repo.path("users").read_text())["items"]] == ["usr_keep"]


def test_r2_3_single_backup_when_several_collections_migrate(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("users", "categories"):
        _write_raw(data_dir, name, {"schema_version": 0, "items": []})
    with Repository(data_dir):
        pass
    backups = list((data_dir / ".backups").iterdir())
    assert len(backups) == 1


def test_manual_backups_are_never_rotated(data_dir: Path, ticking_clock: None) -> None:
    with Repository(data_dir, backups_keep=1) as repo:
        repo.put("users", make_user())
        manual = repo.backup(reason="manual")
        repo.backup()
        last = repo.backup()
    names = sorted(p.name for p in (data_dir / ".backups").iterdir())
    assert manual is not None and last is not None
    assert names == sorted([manual.name, last.name])
