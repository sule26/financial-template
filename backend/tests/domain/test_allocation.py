"""Split profiles, ownership inheritance, rules, precedence and rounding (docs/08)."""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

import pytest
from builders import ANA, EU, PAIS, Builders
from hypothesis import given
from hypothesis import strategies as st

from expense_tracker.domain.allocation import (
    AllocationError,
    LinkedDefaults,
    RuleInput,
    apply_precedence,
    equivalent,
    income_for,
    main_card_id,
    parts,
    remainder_index,
    resolve_account,
    resolve_allocation,
    resolve_card,
    resolve_split,
    rule_allocation,
    rule_category,
)
from expense_tracker.domain.models import Share

D = Decimal
mk = Builders


def pcts(resolved_shares: tuple[Share, ...]) -> dict[str, Decimal]:
    return {s.user_id: s.pct for s in resolved_shares}


# ---------------------------------------------------------------- income


def test_r1_5_income_in_force_is_greatest_from_month() -> None:
    # docs/07#renda
    user = mk.user(EU, income=[("2026-01", "9000"), ("2027-03", "9500")])
    assert income_for(user, "2025-12") is None
    assert income_for(user, "2027-02") == D("9000.00")
    assert income_for(user, "2027-03") == D("9500.00")


def test_r1_5_income_zero_means_no_income() -> None:
    user = mk.user(EU, income=[("2026-01", "9000"), ("2026-06", "0")])
    assert income_for(user, "2026-07") is None


def test_r11_2_benefit_income_is_separate() -> None:
    user = mk.user(EU, income=[("2026-01", "9000")], benefit=[("2026-01", "800")])
    assert income_for(user, "2026-05", benefit=True) == D("800.00")
    assert income_for(mk.user(ANA), "2026-05", benefit=True) is None


# ---------------------------------------------------------------- split profiles


CASAL_FIXED = mk.split(
    "split_casal", [("2026-01", [(EU, 60), (ANA, 40)]), ("2027-03", [(EU, 55), (ANA, 45)])]
)


@pytest.mark.parametrize(
    ("month", "eu", "ana"),
    [("2025-06", "60", "40"), ("2026-01", "60", "40"), ("2027-02", "60", "40"),
     ("2027-03", "55", "45"), ("2030-01", "55", "45")],
)  # fmt: skip
def test_r6_11_fixed_split_uses_version_in_force(month: str, eu: str, ana: str) -> None:
    # docs/08#modo-fixo-com-histórico-r611 (before first version -> first version)
    resolved = resolve_split(CASAL_FIXED, month, {})
    assert pcts(resolved.shares) == {EU: D(eu), ANA: D(ana)}
    assert resolved.warnings == ()


def _proportional(eu_income: list[tuple[str, str]], ana_income: list[tuple[str, str]]) -> tuple:
    users = {
        EU: mk.user(EU, "Eu", income=eu_income),
        ANA: mk.user(ANA, "Esposa", income=ana_income),
    }
    profile = mk.split(
        "split_renda",
        [("2026-01", [(EU, 60), (ANA, 40)]), ("2027-06", [(EU, 70), (ANA, 30)])],
        mode="income_proportional",
    )
    return profile, users


def test_r6_12_proportional_split_follows_income() -> None:
    # docs/08#modo-proporcional-à-renda-r612: 9000/6000 -> 60/40; wife 7500 from 2027-03 ->
    # 54,55/45,45 from 2027-03
    profile, users = _proportional(
        [("2026-01", "9000")], [("2026-01", "6000"), ("2027-03", "7500")]
    )
    assert pcts(resolve_split(profile, "2027-02", users).shares) == {EU: D("60"), ANA: D("40")}
    resolved = resolve_split(profile, "2027-03", users)
    assert pcts(resolved.shares) == {EU: D("54.55"), ANA: D("45.45")}
    assert sum(s.pct for s in resolved.shares) == D("100.00")
    assert resolved.warnings == ()


def test_r6_12_proportional_residue_goes_to_highest_income() -> None:
    users = {
        "a": mk.user("a", income=[("2026-01", "1000")]),
        "b": mk.user("b", income=[("2026-01", "1000")]),
        "c": mk.user("c", income=[("2026-01", "2000")]),
    }
    profile = mk.split("s", [("2026-01", [("a", 25), ("b", 25), ("c", 50)])], "income_proportional")
    # 25/25/50 exact; now an inexact one: 1/1/1 -> 33.33 each, residue 0.01 to first (tie)
    assert pcts(resolve_split(profile, "2026-01", users).shares) == {
        "a": D("25"),
        "b": D("25"),
        "c": D("50"),
    }
    equal = {u: mk.user(u, income=[("2026-01", "100")]) for u in ("a", "b", "c")}
    got = pcts(resolve_split(profile, "2026-01", equal).shares)
    assert got == {"a": D("33.34"), "b": D("33.33"), "c": D("33.33")}
    # highest income takes the residue even when not first
    top_last = {
        "a": mk.user("a", income=[("2026-01", "100")]),
        "b": mk.user("b", income=[("2026-01", "100")]),
        "c": mk.user("c", income=[("2026-01", "400")]),
    }
    got = pcts(resolve_split(profile, "2026-01", top_last).shares)
    assert sum(got.values()) == D("100.00")
    # 16,67 + 16,67 + 66,67 = 100,01 -> the top earner absorbs -0,01
    assert got == {"a": D("16.67"), "b": D("16.67"), "c": D("66.66")}


@pytest.mark.parametrize(
    ("ana_income", "month", "expected"),
    [
        ([], "2026-05", {EU: D("60"), ANA: D("40")}),  # no income at all
        ([("2026-01", "0")], "2026-05", {EU: D("60"), ANA: D("40")}),  # zero income
        ([], "2027-07", {EU: D("70"), ANA: D("30")}),  # fallback uses version in force
    ],
)
def test_r6_12_proportional_falls_back_to_fixed_version_without_income(
    ana_income: list[tuple[str, str]], month: str, expected: dict[str, Decimal]
) -> None:
    # docs/08: without income (or 0.00) -> history version in force in M + warning
    profile, users = _proportional([("2026-01", "9000")], ana_income)
    resolved = resolve_split(profile, month, users)
    assert pcts(resolved.shares) == expected
    assert resolved.warnings == (f"proporção fixa usada: renda de Esposa ausente em {month}",)


def test_r6_12_proportional_unknown_member_falls_back() -> None:
    profile, users = _proportional([("2026-01", "9000")], [("2026-01", "6000")])
    resolved = resolve_split(profile, "2026-05", {EU: users[EU]})
    assert pcts(resolved.shares) == {EU: D("60"), ANA: D("40")}
    assert ANA in resolved.warnings[0]


def test_r6_10_resolve_allocation_fixed_and_split_ref() -> None:
    fixed = mk.shares((EU, 50), (ANA, 50))
    assert resolve_allocation(fixed, "2026-01", {}, {}).shares == tuple(fixed)
    splits = {"split_casal": CASAL_FIXED}
    got = resolve_allocation(mk.ref("split_casal"), "2027-03", splits, {})
    assert pcts(got.shares) == {EU: D("55"), ANA: D("45")}
    with pytest.raises(AllocationError):
        resolve_allocation(mk.ref("split_nope"), "2027-03", splits, {})


def test_r5_4_equivalent_compares_resolved_shares() -> None:
    splits = {"split_casal": CASAL_FIXED}
    ref = mk.ref("split_casal")
    assert equivalent(ref, mk.shares((ANA, 40), (EU, 60)), "2026-05", splits, {})
    assert not equivalent(ref, mk.shares((ANA, 40), (EU, 60)), "2027-05", splits, {})


# ---------------------------------------------------------------- owners and responsible


def test_r6_7_my_card_everything_mine() -> None:
    # docs/08#donos-e-responsável row 1
    own = resolve_card(mk.card("card_eu"), {}, {})
    assert own.owners == mk.shares((EU, 100))
    assert own.responsible_user_id == EU
    assert own.owners_origin == "owners:card"


def test_r6_7_joint_card_split_50_50_responsible_me() -> None:
    # row 2: joint account card, eu 50 / Ana 50, responsible eu
    card = mk.card("card_conj", owners=mk.shares((EU, 50), (ANA, 50)), responsible=EU)
    own = resolve_card(card, {}, {})
    assert own.owners == mk.shares((EU, 50), (ANA, 50))
    assert own.responsible_user_id == EU


def test_r6_9_card_inherits_owners_and_responsible_from_account() -> None:
    # row 3: joint account 60/40 with Ana responsible; card without own owners inherits
    acc = mk.account("acc_conj", owners=mk.shares((EU, 60), (ANA, 40)), responsible=ANA)
    card = mk.card("card_conj", account="acc_conj", responsible=None)
    own = resolve_card(card, {}, {"acc_conj": acc})
    assert own.owners == mk.shares((EU, 60), (ANA, 40))
    assert own.responsible_user_id == ANA
    assert own.owners_origin == "owners:account"


def test_r6_8_responsible_need_not_be_an_owner() -> None:
    # row 4: my card used by my parents: owners pais 100, responsible eu
    card = mk.card("card_pais", owners=mk.shares((PAIS, 100)), responsible=EU)
    own = resolve_card(card, {}, {})
    assert own.owners == mk.shares((PAIS, 100))
    assert own.responsible_user_id == EU


def test_r1_10_additional_card_own_owners_inherits_responsible_from_main() -> None:
    # row 5: additional used by parents; responsible inherited from main card
    main = mk.card("card_main", owners=mk.shares((EU, 100)), responsible=EU)
    extra = mk.card("card_add", parent="card_main", owners=mk.shares((PAIS, 100)), responsible=None)
    own = resolve_card(extra, {"card_main": main}, {})
    assert own.owners == mk.shares((PAIS, 100))
    assert own.responsible_user_id == EU
    assert own.owners_origin == "owners:card"
    assert main_card_id(extra) == "card_main"
    assert main_card_id(main) == "card_main"


def test_r6_9_inheritance_chain_additional_main_account_each_field_separately() -> None:
    # additional <- main <- account; owners from the account, responsible from the main
    acc = mk.account("acc", owners=mk.shares((EU, 50), (ANA, 50)), responsible=ANA)
    main = mk.card("card_main", account="acc", responsible=EU)
    extra = mk.card("card_add", parent="card_main", responsible=None)
    own = resolve_card(extra, {"card_main": main}, {"acc": acc})
    assert own.owners == mk.shares((EU, 50), (ANA, 50))
    assert own.responsible_user_id == EU
    assert own.owners_origin == "owners:account"
    # additional inherits owners from main when main has them
    main2 = mk.card("card_main", owners=mk.shares((ANA, 100)), responsible=ANA)
    own2 = resolve_card(extra, {"card_main": main2}, {})
    assert own2.owners == mk.shares((ANA, 100))
    assert own2.owners_origin == "owners:account"


def test_resolve_card_errors() -> None:
    with pytest.raises(AllocationError, match="parent"):
        resolve_card(mk.card("c", parent="ghost"), {}, {})
    with pytest.raises(AllocationError, match="account"):
        resolve_card(mk.card("c", account="ghost"), {}, {})
    lonely = mk.card("c2", parent="m", responsible=None)
    bare_main = mk.card("m", owners=mk.shares((EU, 100)), responsible=None)
    with pytest.raises(AllocationError, match="responsible"):
        resolve_card(lonely, {"m": bare_main}, {})
    no_owner_main = mk.card("m", account=None, responsible=EU).model_copy(update={"owners": None})
    with pytest.raises(AllocationError, match="no owners"):
        resolve_card(lonely, {"m": no_owner_main}, {})


def test_resolve_account() -> None:
    acc = mk.account("acc", owners=mk.shares((EU, 60), (ANA, 40)), responsible=ANA)
    own = resolve_account(acc)
    assert (own.responsible_user_id, own.owners_origin) == (ANA, "owners:account")


# ---------------------------------------------------------------- rules (two passes)


def test_r5_3_rule_pass_1_lowest_priority_wins_ignoring_category_condition() -> None:
    rules = [
        mk.rule("r_b", priority=10, when={"description_regex": "MERCADO"}, category="cat_b"),
        mk.rule("r_a", priority=20, when={"description_regex": "MERC"}, category="cat_a"),
        mk.rule("r_cond", priority=1, when={"category_id": "cat_zzz"}, category="cat_c"),
    ]
    item = RuleInput("Mercado Central", D("50"))
    # r_cond has a category condition; in pass 1 that condition is ignored, so it matches first
    assert rule_category(rules, item).id == "r_cond"  # type: ignore[union-attr]
    assert rule_category(rules[:2], item).id == "r_b"  # type: ignore[union-attr]


def test_r5_3_rule_priority_tie_breaks_by_lowest_id() -> None:
    rules = [
        mk.rule("r_2", priority=5, category="cat_2"),
        mk.rule("r_1", priority=5, category="cat_1"),
    ]
    assert rule_category(rules, RuleInput("X", D("1"))).id == "r_1"  # type: ignore[union-attr]


def test_r5_3_rule_pass_2_uses_category_from_pass_1() -> None:
    casal = mk.ref("split_casal")
    rules = [
        mk.rule("r_cat", priority=1, when={"description_regex": "MERCADO"}, category="cat_mercado"),
        mk.rule("r_other", priority=1, when={"category_id": "cat_farmacia"}, allocations=casal),
        mk.rule("r_split", priority=2, when={"category_id": "cat_mercado"}, allocations=casal),
    ]
    item = RuleInput("MERCADO", D("200"))
    cat_rule = rule_category(rules, item)
    assert cat_rule is not None and cat_rule.then.category_id == "cat_mercado"
    alloc_rule = rule_allocation(rules, item, "cat_mercado")
    assert alloc_rule is not None and alloc_rule.id == "r_split"
    assert rule_allocation(rules, item, None) is None


def test_rule_conditions_disabled_card_account_amount_and_bad_regex() -> None:
    item = RuleInput("Uber trip", D("-30.00"), card_id="card_x")
    assert rule_category([mk.rule("r", enabled=False, category="c")], item) is None
    assert rule_category([mk.rule("r", when={"card_id": "card_y"}, category="c")], item) is None
    assert rule_category([mk.rule("r", when={"account_id": "acc"}, category="c")], item) is None
    assert (
        rule_category([mk.rule("r", when={"description_regex": "("}, category="c")], item) is None
    )
    assert (
        rule_category([mk.rule("r", when={"description_regex": "taxi"}, category="c")], item)
        is None
    )
    # min/max are inclusive and compare the absolute value
    assert rule_category([mk.rule("r", when={"min_amount": "30.00"}, category="c")], item)
    assert rule_category([mk.rule("r", when={"max_amount": "30.00"}, category="c")], item)
    assert rule_category([mk.rule("r", when={"min_amount": "30.01"}, category="c")], item) is None
    assert rule_category([mk.rule("r", when={"max_amount": "29.99"}, category="c")], item) is None
    # a rule without then.category_id is not a category rule
    assert rule_category([mk.rule("r", allocations=mk.ref("s"))], item) is None


# ---------------------------------------------------------------- precedence (5 levels)


OWN_CARD = resolve_card(mk.card("card_x", owners=mk.shares((EU, 100))), {}, {})
INHERITED = resolve_card(
    mk.card("card_x", account="acc", responsible=None),
    {},
    {"acc": mk.account("acc", owners=mk.shares((EU, 50), (ANA, 50)))},
)
RULES = [
    mk.rule(
        "r_mercado",
        priority=1,
        when={"description_regex": "MERCADO"},
        category="cat_rule",
        allocations=mk.ref("split_casal"),
    )
]
ITEM = RuleInput("MERCADO X", D("100"), card_id="card_x")
PLAN = LinkedDefaults("plan:plan_1", mk.shares((ANA, 100)), "cat_plan")


def test_r5_3_level_1_manual_annotation_wins() -> None:
    got = apply_precedence(
        ITEM, OWN_CARD, RULES, mk.shares((PAIS, 100)), "cat_manual", PLAN, lambda _: "cat_hist"
    )
    assert (got.allocation_origin, got.allocations) == ("manual", mk.shares((PAIS, 100)))
    assert (got.category_id, got.category_origin) == ("cat_manual", "manual")


def test_r5_3_level_2_linked_plan_subscription_or_recurring() -> None:
    got = apply_precedence(ITEM, OWN_CARD, RULES, linked=PLAN)
    assert (got.allocation_origin, got.allocations) == ("plan:plan_1", mk.shares((ANA, 100)))
    assert (got.category_id, got.category_origin) == ("cat_plan", "plan:plan_1")


def test_r5_3_level_2_linked_without_split_falls_through_to_rule() -> None:
    linked = LinkedDefaults("subscription:sub_1", None, None)
    got = apply_precedence(ITEM, OWN_CARD, RULES, linked=linked)
    assert got.allocation_origin == "rule:r_mercado"
    assert (got.category_id, got.category_origin) == ("cat_rule", "rule:r_mercado")


def test_r5_3_level_3_rule() -> None:
    got = apply_precedence(ITEM, OWN_CARD, RULES)
    assert (got.allocation_origin, got.allocations) == ("rule:r_mercado", mk.ref("split_casal"))


def test_r5_3_level_4_own_card_owners() -> None:
    got = apply_precedence(RuleInput("PADARIA", D("10")), OWN_CARD, RULES)
    assert (got.allocation_origin, got.allocations) == ("owners:card", mk.shares((EU, 100)))
    assert got.category_id is None and got.category_origin is None


def test_r5_3_level_5_inherited_owners() -> None:
    got = apply_precedence(RuleInput("PADARIA", D("10")), INHERITED, RULES)
    assert got.allocation_origin == "owners:account"
    assert got.allocations == mk.shares((EU, 50), (ANA, 50))


def test_r1_11_category_falls_back_to_last_used_with_same_description() -> None:
    seen: list[str] = []

    def last(desc: str) -> str | None:
        seen.append(desc)
        return "cat_hist" if desc == "PADARIA" else None

    got = apply_precedence(
        RuleInput("Padaria 01/03", D("10")), OWN_CARD, RULES, last_category_for=last
    )
    assert (got.category_id, got.category_origin) == ("cat_hist", "history")
    assert seen == ["PADARIA"]
    got = apply_precedence(RuleInput("Outra", D("10")), OWN_CARD, RULES, last_category_for=last)
    assert got.category_id is None


# ---------------------------------------------------------------- rounding


def test_r6_2_rounding_100_in_thirds_responsible_first() -> None:
    # docs/08#arredondamento: R$ 100,00 by 33,34/33,33/33,33 -> 33,34 + 33,33 + 33,33
    shares = mk.shares((EU, "33.34"), (ANA, "33.33"), (PAIS, "33.33"))
    assert parts(D("100.00"), shares, EU) == {EU: D("33.34"), ANA: D("33.33"), PAIS: D("33.33")}


def test_r6_2_rounding_10_in_thirds_responsible_takes_the_cent() -> None:
    # docs/08#arredondamento: R$ 10,00 -> 3,33 x3 = 9,99 -> responsible gets 3,34
    shares = mk.shares((EU, "33.34"), (ANA, "33.33"), (PAIS, "33.33"))
    assert parts(D("10.00"), shares, EU) == {EU: D("3.34"), ANA: D("3.33"), PAIS: D("3.33")}
    assert parts(D("10.00"), shares, PAIS) == {EU: D("3.33"), ANA: D("3.33"), PAIS: D("3.34")}


def test_r6_2_rounding_responsible_outside_split_goes_to_largest_pct_first_on_tie() -> None:
    shares = mk.shares((ANA, "33.33"), (PAIS, "33.34"), (EU, "33.33"))
    assert remainder_index(shares, "usr_outside") == 1
    tie = mk.shares((ANA, "50"), (PAIS, "50"))
    assert remainder_index(tie, "usr_outside") == 0
    assert parts(D("0.01"), tie, "usr_outside") == {ANA: D("0.01"), PAIS: D("0.00")}


@st.composite
def share_lists(draw: st.DrawFn) -> list[Share]:
    k = draw(st.integers(min_value=1, max_value=5))
    cuts = sorted(set(draw(st.lists(st.integers(1, 9_999), min_size=k - 1, max_size=k - 1))))
    bounds = [0, *cuts, 10_000]
    values = [b - a for a, b in pairwise(bounds)]
    return [Share(user_id=f"u{i}", pct=D(v) / 100) for i, v in enumerate(values)]


@given(
    amount=st.integers(-10_000_000, 10_000_000).map(lambda c: D(c) / 100),
    shares=share_lists(),
    responsible=st.sampled_from(["u0", "u1", "u2", "u_outside"]),
)
def test_r6_2_parts_sum_exactly_to_amount(
    amount: Decimal, shares: list[Share], responsible: str
) -> None:
    result = parts(amount, shares, responsible)
    assert sum(result.values(), D("0")) == amount
    assert set(result) == {s.user_id for s in shares}
