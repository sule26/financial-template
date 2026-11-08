"""Operator feedback round: work benefits (R11.5, R11.6), deleting linked users, default
categories (R1.11) and per-person projection/summary states (R4.8, R1.13).

Written against the contract (docs/specs), not against the implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from api_helpers import CSRF, Api, error_code
from fastapi.testclient import TestClient

from expense_tracker.api.app import create_app
from expense_tracker.clock import FixedClock
from expense_tracker.config import Settings
from expense_tracker.domain.models import Annotation

DEFAULT_NAMES = [
    "Alimentação",
    "Aluguel",
    "Animais",
    "Banco",
    "Casa",
    "Compras",
    "Delivery",
    "Digital",
    "Educação",
    "Entretenimento",
    "Família",
    "Lazer",
    "Moradia",
    "Outros",
    "Pessoal",
    "Presente",
    "Saúde",
    "Trabalho",
    "Transporte",
]


def _benefit(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "VR",
        "user_id": "usr_ana",
        "destination": "card",
        "account_id": "acc_vr",
        "amount_history": [{"from_month": "2026-01", "amount": "800.00"}],
        "active": True,
    }
    body.update(over)
    return body


def _month(api: Api, month: str, user_id: str = "usr_ana") -> dict[str, Any]:
    """The ``series`` entry of the summary for ``month`` (income lives per month)."""
    r = api.get("/api/reports/summary", params={"month": month, "user_id": user_id})
    assert r.status_code == 200, r.text
    series = {s["month"]: s for s in r.json()["series"]}
    return series[month]  # type: ignore[no-any-return]


# ---------------------------------------------------------------- R11.5 benefits CRUD


def test_r11_5_r13_5_create_card_benefit_on_benefit_account(world: Api) -> None:
    created = world.create("benefits", _benefit())
    assert created["id"].startswith("ben_")
    assert created["name"] == "VR"
    assert created["destination"] == "card"
    assert created["account_id"] == "acc_vr"
    listed = world.get("/api/benefits").json()
    assert [b["id"] for b in listed] == [created["id"]]
    assert world.get(f"/api/benefits/{created['id']}").status_code == 200


def test_r11_5_create_account_benefit_on_checking_account(world: Api) -> None:
    created = world.create(
        "benefits",
        _benefit(
            id="ben_home",
            name="Auxílio home office",
            destination="account",
            account_id="acc_cc",
            amount_history=[{"from_month": "2026-01", "amount": "150.00"}],
        ),
    )
    assert created["id"] == "ben_home"
    assert created["destination"] == "account"


@pytest.mark.parametrize(
    ("destination", "account_id"),
    [
        ("card", "acc_cc"),  # card benefit on a checking account
        ("card", "acc_cash"),
        ("account", "acc_vr"),  # account benefit on a benefit account
        ("account", "acc_cash"),
    ],
)
def test_r11_5_benefit_destination_requires_matching_account_type(
    world: Api, destination: str, account_id: str
) -> None:
    r = world.post("/api/benefits", _benefit(destination=destination, account_id=account_id))
    assert r.status_code == 422, r.text
    assert error_code(r) == "benefit_account_type"
    assert world.get("/api/benefits").json() == []


def test_r11_5_benefit_with_unknown_user_is_rejected(world: Api) -> None:
    r = world.post("/api/benefits", _benefit(user_id="usr_ghost"))
    assert r.status_code == 422, r.text
    assert world.get("/api/benefits").json() == []


def test_r11_5_benefit_with_unknown_account_is_rejected(world: Api) -> None:
    r = world.post("/api/benefits", _benefit(account_id="acc_ghost"))
    assert r.status_code == 422, r.text


def test_r11_5_benefit_update_also_validates_account_type(world: Api) -> None:
    world.create("benefits", _benefit(id="ben_vr"))
    r = world.put("/api/benefits/ben_vr", _benefit(account_id="acc_cc"))
    assert r.status_code == 422
    assert error_code(r) == "benefit_account_type"
    assert world.get("/api/benefits/ben_vr").json()["account_id"] == "acc_vr"


# ---------------------------------------------------------------- R11.6 benefits in income


def test_r11_6_account_benefit_counts_as_income_card_benefit_as_benefit_income(
    world: Api,
) -> None:
    world.create(
        "benefits",
        _benefit(
            name="Auxílio home office",
            destination="account",
            account_id="acc_cc",
            amount_history=[{"from_month": "2026-01", "amount": "150.00"}],
        ),
    )
    world.create("benefits", _benefit())
    oct_ = _month(world, "2026-10")
    assert oct_["income"] == "150.00"
    assert oct_["benefit_income"] == "800.00"


def test_r11_6_account_benefit_adds_to_salary(world: Api) -> None:
    world.put(
        "/api/users/usr_ana",
        {"name": "Ana", "income_history": [{"from_month": "2026-01", "amount": "5000.00"}]},
    )
    world.create(
        "benefits",
        _benefit(
            name="Auxílio home office",
            destination="account",
            account_id="acc_cc",
            amount_history=[{"from_month": "2026-01", "amount": "150.00"}],
        ),
    )
    assert _month(world, "2026-10")["income"] == "5150.00"


def test_r11_6_two_named_benefits_are_kept_apart_and_summed(world: Api) -> None:
    world.create("benefits", _benefit(id="ben_vr", name="VR"))
    world.create(
        "benefits",
        _benefit(
            id="ben_va", name="VA", amount_history=[{"from_month": "2026-01", "amount": "300.00"}]
        ),
    )
    names = {b["id"]: b["name"] for b in world.get("/api/benefits").json()}
    assert names == {"ben_vr": "VR", "ben_va": "VA"}
    assert _month(world, "2026-10")["benefit_income"] == "1100.00"


def test_r11_6_benefit_amount_follows_from_month(world: Api) -> None:
    world.create(
        "benefits",
        _benefit(
            amount_history=[
                {"from_month": "2026-03", "amount": "800.00"},
                {"from_month": "2026-10", "amount": "900.00"},
            ]
        ),
    )
    assert _month(world, "2026-02")["benefit_income"] is None  # before the benefit began
    assert _month(world, "2026-09")["benefit_income"] == "800.00"
    assert _month(world, "2026-10")["benefit_income"] == "900.00"


def test_r11_6_inactive_benefit_does_not_count(world: Api) -> None:
    world.create("benefits", _benefit(active=False))
    world.create(
        "benefits",
        _benefit(
            name="Auxílio home office",
            destination="account",
            account_id="acc_cc",
            amount_history=[{"from_month": "2026-01", "amount": "150.00"}],
            active=False,
        ),
    )
    oct_ = _month(world, "2026-10")
    assert oct_["income"] is None
    assert oct_["benefit_income"] is None


def test_r11_6_benefit_belongs_only_to_its_user(world: Api) -> None:
    world.create("benefits", _benefit())
    assert _month(world, "2026-10", user_id="usr_bia")["benefit_income"] is None


def test_r11_6_committed_income_in_projection_uses_benefits(world: Api) -> None:
    world.create(
        "benefits",
        _benefit(
            name="Auxílio home office",
            destination="account",
            account_id="acc_cc",
            amount_history=[{"from_month": "2026-01", "amount": "150.00"}],
        ),
    )
    world.create("benefits", _benefit())
    proj = world.get("/api/reports/projection", params={"user_id": "usr_ana"}).json()
    commit = proj["committed_income"]
    assert [c["user_id"] for c in commit] == ["usr_ana"]
    first = commit[0]["months"][0]
    assert first["month"] == "2026-10"
    assert first["income"] == "150.00"
    assert first["benefit_income"] == "800.00"


def test_r11_6_projection_without_any_income_has_no_commitment(world: Api) -> None:
    world.create("benefits", _benefit(active=False))
    proj = world.get("/api/reports/projection", params={"user_id": "usr_ana"}).json()
    assert proj["committed_income"] == []


# ---------------------------------------------------------------- deleting linked users

CAIO = "usr_caio"
CAIO_ONLY = [{"user_id": CAIO, "pct": "100.00"}]


def _link_benefit(api: Api) -> str:
    api.create("benefits", _benefit(id="ben_caio", user_id=CAIO))
    return "benefits/ben_caio"


def _link_account(api: Api) -> str:
    api.create(
        "accounts",
        {
            "id": "acc_caio",
            "name": "Conta do Caio",
            "type": "checking",
            "owners": CAIO_ONLY,
            "responsible_user_id": CAIO,
        },
    )
    return "accounts/acc_caio"


def _link_card(api: Api) -> str:
    api.create(
        "cards",
        {
            "id": "card_caio",
            "name": "Cartão do Caio",
            "owners": CAIO_ONLY,
            "responsible_user_id": CAIO,
            "billing_history": [{"from_month": "2026-01", "closing_day": 3, "due_day": 10}],
        },
    )
    return "cards/card_caio"


def _link_split(api: Api) -> str:
    api.create(
        "split-profiles",
        {
            "id": "split_caio",
            "name": "Ana e Caio",
            "members": ["usr_ana", CAIO],
            "history": [
                {
                    "from_month": "2026-01",
                    "shares": [
                        {"user_id": "usr_ana", "pct": "60.00"},
                        {"user_id": CAIO, "pct": "40.00"},
                    ],
                }
            ],
        },
    )
    return "split_profiles/split_caio"


def _link_transaction(api: Api) -> str:
    r = api.post(
        "/api/transactions",
        {
            "purchase_date": "2026-10-05",
            "amount": "100.00",
            "description": "MERCADO",
            "category_id": "cat_food",
            "card_id": "card_main",
            "allocations": CAIO_ONLY,
        },
    )
    assert r.status_code == 201, r.text
    return f"transactions/{r.json()['transaction']['id']}"


def _link_annotation(api: Api) -> str:
    api.repo.put(
        "annotations",
        Annotation.model_validate({"fingerprint": "fp_caio", "allocations": CAIO_ONLY}),
    )
    return "annotations/fp_caio"


def _link_settlement(api: Api) -> str:
    api.create(
        "settlements",
        {
            "id": "set_caio",
            "from_user_id": CAIO,
            "to_user_id": "usr_ana",
            "amount": "10.00",
            "date": "2026-10-01",
            "month": "2026-10",
        },
    )
    return "settlements/set_caio"


def _link_investment(api: Api) -> str:
    api.create("investments", {"id": "inv_caio", "name": "CDB", "owners": CAIO_ONLY})
    return "investments/inv_caio"


LINKS: dict[str, Callable[[Api], str]] = {
    "benefit": _link_benefit,
    "account": _link_account,
    "card": _link_card,
    "split_profile": _link_split,
    "transaction": _link_transaction,
    "annotation": _link_annotation,
    "settlement": _link_settlement,
    "investment": _link_investment,
}


@pytest.mark.parametrize("link", list(LINKS), ids=list(LINKS))
def test_r11_5_r13_6_delete_user_with_links_is_conflict(world: Api, link: str) -> None:
    world.create("users", {"id": CAIO, "name": "Caio"})
    ref = LINKS[link](world)
    r = world.delete(f"/api/users/{CAIO}")
    assert r.status_code == 409, r.text
    assert error_code(r) == "in_use"
    assert ref in r.json()["error"]["details"]["referenced_by"]
    assert world.get(f"/api/users/{CAIO}").status_code == 200


def test_r11_5_delete_user_lists_every_link(world: Api) -> None:
    world.create("users", {"id": CAIO, "name": "Caio"})
    refs = {make(world) for make in LINKS.values()}
    r = world.delete(f"/api/users/{CAIO}")
    assert r.status_code == 409
    assert refs <= set(r.json()["error"]["details"]["referenced_by"])


def test_r11_5_delete_user_without_links_succeeds(world: Api) -> None:
    world.create("users", {"id": CAIO, "name": "Caio"})
    r = world.delete(f"/api/users/{CAIO}")
    assert r.status_code == 200, r.text
    assert world.get(f"/api/users/{CAIO}").status_code == 404


def test_r11_5_delete_user_after_removing_benefit_succeeds(world: Api) -> None:
    world.create("users", {"id": CAIO, "name": "Caio"})
    _link_benefit(world)
    assert world.delete(f"/api/users/{CAIO}").status_code == 409
    assert world.delete("/api/benefits/ben_caio").status_code == 200
    assert world.delete(f"/api/users/{CAIO}").status_code == 200


# ---------------------------------------------------------------- R1.11 default categories


def _client(settings: Settings, clock: FixedClock) -> TestClient:
    return TestClient(create_app(settings=settings, clock=clock, start_background=False))


def _names(c: TestClient) -> list[str]:
    return [cat["name"] for cat in c.get("/api/categories").json()]


def test_r1_11_r13_7_fresh_app_seeds_exactly_the_default_categories(
    settings: Settings, clock: FixedClock
) -> None:
    with _client(settings, clock) as c:
        cats = c.get("/api/categories").json()
    assert [cat["name"] for cat in cats] == DEFAULT_NAMES
    assert len({cat["id"] for cat in cats}) == 19


def test_r1_11_restart_does_not_duplicate_defaults(settings: Settings, clock: FixedClock) -> None:
    with _client(settings, clock) as c:
        first = c.get("/api/categories").json()
    with _client(settings, clock) as c:
        assert c.get("/api/categories").json() == first


def test_r1_11_deleted_defaults_are_not_recreated_on_restart(
    settings: Settings, clock: FixedClock
) -> None:
    with _client(settings, clock) as c:
        cats = c.get("/api/categories").json()
        for cat in cats[:5]:
            r = c.delete(f"/api/categories/{cat['id']}", headers=CSRF)
            assert r.status_code == 200, r.text
    with _client(settings, clock) as c:
        assert _names(c) == DEFAULT_NAMES[5:]


def test_r1_11_all_deleted_stays_empty_after_restart(settings: Settings, clock: FixedClock) -> None:
    with _client(settings, clock) as c:
        for cat in c.get("/api/categories").json():
            assert c.delete(f"/api/categories/{cat['id']}", headers=CSRF).status_code == 200
        assert _names(c) == []
    with _client(settings, clock) as c:
        assert _names(c) == []


def test_r1_11_user_categories_survive_and_defaults_are_not_added_later(
    settings: Settings, clock: FixedClock
) -> None:
    with _client(settings, clock) as c:
        for cat in c.get("/api/categories").json():
            c.delete(f"/api/categories/{cat['id']}", headers=CSRF)
        r = c.post("/api/categories", json={"id": "cat_mine", "name": "Minha"}, headers=CSRF)
        assert r.status_code == 201, r.text
    with _client(settings, clock) as c:
        assert _names(c) == ["Minha"]


# ---------------------------------------------------------------- R4.8 / R1.13 per person


@pytest.fixture
def two_people(api: Api) -> Api:
    api.create("users", {"id": "usr_a", "name": "Alice"})
    api.create("users", {"id": "usr_b", "name": "Bruno"})
    api.create("categories", {"id": "cat_x", "name": "Teste"})
    billing = [{"from_month": "2026-01", "closing_day": 3, "due_day": 10}]
    for uid, card in (("usr_a", "card_a"), ("usr_b", "card_b")):
        api.create(
            "cards",
            {
                "id": card,
                "name": f"Cartão {uid}",
                "owners": [{"user_id": uid, "pct": "100.00"}],
                "responsible_user_id": uid,
                "billing_history": billing,
            },
        )
        r = api.post(
            "/api/transactions",
            {
                "purchase_date": "2026-10-05",
                "amount": "100.00",
                "description": "MERCADO",
                "category_id": "cat_x",
                "card_id": card,
            },
        )
        assert r.status_code == 201, r.text
    return api


def test_r4_8_r13_4_projection_states_only_for_the_persons_cards(two_people: Api) -> None:
    proj = two_people.get("/api/reports/projection", params={"user_id": "usr_a"}).json()
    assert proj["months"]
    for m in proj["months"]:
        assert "card_b" not in m["states"], m
        assert "card_b" not in m["by_card"], m
    assert any("card_a" in m["states"] for m in proj["months"])


def test_r4_8_projection_without_user_has_all_states(two_people: Api) -> None:
    proj = two_people.get("/api/reports/projection").json()
    keys = set().union(*(m["states"] for m in proj["months"]))
    assert {"card_a", "card_b"} <= keys


def test_r1_13_summary_states_filtered_by_person(two_people: Api) -> None:
    mine = two_people.get(
        "/api/reports/summary", params={"month": "2026-11", "user_id": "usr_b"}
    ).json()
    assert "card_a" not in mine["states"]
    assert "card_a" not in mine["by_card"]
    assert "card_b" in mine["states"]
    full = two_people.get("/api/reports/summary", params={"month": "2026-11"}).json()
    assert {"card_a", "card_b"} <= set(full["states"])
    assert {"card_a", "card_b"} <= set(full["by_card"])


def test_r1_13_responsible_person_sees_the_card_state(api: Api) -> None:
    """Responsible (not owner) also counts as "the person's" card."""
    api.create("users", {"id": "usr_a", "name": "Alice"})
    api.create("users", {"id": "usr_b", "name": "Bruno"})
    api.create(
        "cards",
        {
            "id": "card_kid",
            "name": "Cartão do filho",
            "owners": [{"user_id": "usr_b", "pct": "100.00"}],
            "responsible_user_id": "usr_a",
            "billing_history": [{"from_month": "2026-01", "closing_day": 3, "due_day": 10}],
        },
    )
    proj = api.get("/api/reports/projection", params={"user_id": "usr_a"}).json()
    assert any("card_kid" in m["states"] for m in proj["months"])


def test_r14_24_default_categories_explain_what_goes_in_them(api: Api) -> None:
    cats = {c["name"]: c for c in api.get("/api/categories").json()}
    assert all(c["description"] for c in cats.values())
    assert "luz" in cats["Casa"]["description"]
    assert "Farmácia" in cats["Saúde"]["description"]
    # a category of my own may have a description too, or none
    r = api.post("/api/categories", {"name": "Viagem", "description": "Passagens e hotel"})
    assert r.json()["description"] == "Passagens e hotel"
    assert api.post("/api/categories", {"name": "Sem nota"}).json()["description"] is None


def test_r14_24_existing_default_categories_get_their_description(
    settings: Settings, clock: FixedClock
) -> None:
    def app() -> TestClient:
        return TestClient(create_app(settings=settings, clock=clock, start_background=False))

    with app() as c:  # first run seeds; then simulate an old install without descriptions
        casa = next(x for x in c.get("/api/categories").json() if x["name"] == "Casa")
        r = c.put(f"/api/categories/{casa['id']}", json={**casa, "description": None},
                  headers=CSRF)  # fmt: skip
        assert r.status_code == 200, r.text
        r = c.post("/api/categories", json={"name": "Viagem"}, headers=CSRF)
        assert r.status_code == 201, r.text
    with app() as c:  # next start fills the standard ones in, leaves mine alone
        cats = {x["name"]: x for x in c.get("/api/categories").json()}
    assert "luz" in cats["Casa"]["description"]
    assert cats["Viagem"]["description"] is None
