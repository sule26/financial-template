"""R13.12: each split version chooses its own mode (fixed or income proportional)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from builders import ANA, EU, Builders
from pydantic import ValidationError

from expense_tracker.domain.allocation import resolve_split
from expense_tracker.domain.models import Share, SplitProfile, SplitVersion, User

D = Decimal
mk = Builders


def pcts(shares: tuple[Share, ...]) -> dict[str, Decimal]:
    return {s.user_id: s.pct for s in shares}


def _users(eu: list[tuple[str, str]], ana: list[tuple[str, str]]) -> dict[str, User]:
    return {EU: mk.user(EU, "Eu", income=eu), ANA: mk.user(ANA, "Esposa", income=ana)}


def _version(month: str, mode: str | None, *pairs: tuple[str, int]) -> SplitVersion:
    return SplitVersion.model_validate(
        {
            "from_month": month,
            "mode": mode,
            "shares": [{"user_id": u, "pct": str(p)} for u, p in pairs],
        }
    )


# docs/08 example: 70/30 fixed -> proportional (no percentages) -> 50/50 fixed
DOCS_EXAMPLE = SplitProfile(
    id="split_casal",
    name="Casal",
    members=[EU, ANA],
    history=[
        _version("2026-01", "fixed", (EU, 70), (ANA, 30)),
        _version("2026-06", "income_proportional"),
        _version("2027-01", "fixed", (EU, 50), (ANA, 50)),
    ],
)


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        ("2025-12", {EU: D("70"), ANA: D("30")}),  # before the first version -> first
        ("2026-05", {EU: D("70"), ANA: D("30")}),
        ("2026-06", {EU: D("60"), ANA: D("40")}),  # proportional: 9000/6000
        ("2026-12", {EU: D("60"), ANA: D("40")}),
        ("2027-01", {EU: D("50"), ANA: D("50")}),  # back to fixed
    ],
)
def test_r13_12_mode_comes_from_the_version_in_force(
    month: str, expected: dict[str, Decimal]
) -> None:
    users = _users([("2026-01", "9000")], [("2026-01", "6000")])
    resolved = resolve_split(DOCS_EXAMPLE, month, users)
    assert pcts(resolved.shares) == expected
    assert resolved.warnings == ()


def test_r13_12_proportional_without_income_uses_latest_previous_fixed_version() -> None:
    users = _users([("2026-01", "9000")], [])
    resolved = resolve_split(DOCS_EXAMPLE, "2026-09", users)
    assert pcts(resolved.shares) == {EU: D("70"), ANA: D("30")}
    assert resolved.warnings == ("proporção fixa usada: renda de Esposa ausente em 2026-09",)


def test_r13_12_proportional_first_version_falls_back_to_first_fixed_in_history() -> None:
    profile = SplitProfile(
        id="s",
        name="S",
        members=[EU, ANA],
        history=[
            _version("2026-01", "income_proportional"),
            _version("2026-08", "fixed", (EU, 80), (ANA, 20)),
        ],
    )
    users = _users([("2026-01", "9000")], [("2026-01", "0")])
    resolved = resolve_split(profile, "2026-03", users)
    assert pcts(resolved.shares) == {EU: D("80"), ANA: D("20")}
    assert resolved.warnings == ("proporção fixa usada: renda de Esposa ausente em 2026-03",)


def test_r13_12_no_fixed_version_at_all_splits_equally_with_residue_on_first() -> None:
    profile = SplitProfile(
        id="s",
        name="S",
        members=["a", "b", "c"],
        history=[_version("2026-01", "income_proportional")],
    )
    users = {u: mk.user(u, u.upper()) for u in ("a", "b", "c")}
    resolved = resolve_split(profile, "2026-03", users)
    assert pcts(resolved.shares) == {"a": D("33.34"), "b": D("33.33"), "c": D("33.33")}
    assert resolved.warnings == ("divisão igual usada: renda de A, B, C ausente em 2026-03",)


def test_r13_12_share_rounding_to_zero_uses_fixed_fallback() -> None:
    profile = SplitProfile(
        id="s",
        name="S",
        members=[EU, ANA],
        history=[
            _version("2026-01", "fixed", (EU, 70), (ANA, 30)),
            _version("2026-02", "income_proportional"),
        ],
    )
    users = _users([("2026-01", "1000000")], [("2026-01", "1")])
    resolved = resolve_split(profile, "2026-02", users)
    assert pcts(resolved.shares) == {EU: D("70"), ANA: D("30")}
    assert resolved.warnings == ("proporção fixa usada: renda muito desigual em 2026-02",)


def test_r13_12_legacy_profile_mode_applies_to_versions_without_mode() -> None:
    # Existing data: versions without "mode" follow SplitProfile.mode (compatibility).
    profile = mk.split(
        "split_renda", [("2026-01", [(EU, 60), (ANA, 40)])], mode="income_proportional"
    )
    assert profile.history[0].mode is None
    users = _users([("2026-01", "5000")], [("2026-01", "5000")])
    assert pcts(resolve_split(profile, "2026-03", users).shares) == {EU: D("50"), ANA: D("50")}
    # a version can override the legacy default
    override = profile.model_copy(
        update={"history": [*profile.history, _version("2026-05", "fixed", (EU, 90), (ANA, 10))]}
    )
    assert pcts(resolve_split(override, "2026-06", users).shares) == {EU: D("90"), ANA: D("10")}


def test_r13_12_validation_fixed_needs_shares_proportional_accepts_empty() -> None:
    with pytest.raises(ValidationError, match="fixed split version needs shares"):
        SplitVersion.model_validate({"from_month": "2026-01", "mode": "fixed", "shares": []})
    with pytest.raises(ValidationError, match="must sum to 100"):
        _version("2026-01", "fixed", (EU, 70), (ANA, 20))
    ok = SplitVersion.model_validate({"from_month": "2026-01", "mode": "income_proportional"})
    assert ok.shares == []
    # a version without mode in a fixed profile is fixed -> needs shares
    with pytest.raises(ValidationError, match="fixed split version needs shares"):
        SplitProfile(id="s", name="S", members=[EU], history=[SplitVersion(from_month="2026-01")])
    # ...but is fine in a legacy proportional profile
    legacy = SplitProfile(
        id="s",
        name="S",
        members=[EU],
        mode="income_proportional",
        history=[SplitVersion(from_month="2026-01")],
    )
    assert legacy.mode_of(legacy.history[0]) == "income_proportional"
    # shares of a fixed version must be members of the profile
    with pytest.raises(ValidationError, match="not a member"):
        SplitProfile(
            id="s",
            name="S",
            members=[EU],
            history=[_version("2026-01", "fixed", (EU, 50), (ANA, 50))],
        )
