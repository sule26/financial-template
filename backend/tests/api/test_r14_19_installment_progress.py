"""R14.19: installments show which one they are, how many are left and "terminando"."""

from __future__ import annotations

from api_helpers import Api


def _plan(world: Api, n: int = 5, first: str = "2026-08") -> str:
    r = world.post(
        "/api/installment-plans",
        {
            "card_id": "card_main",
            "description": "TV",
            "total_installments": n,
            "first_invoice_month": first,
            "total_amount": "500.00",
            "category_id": "cat_food",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]  # type: ignore[no-any-return]


def test_r14_19_progress_counts_what_is_left(world: Api) -> None:
    # card_main closes on the 3rd: on 2026-10-12 H = 2026-11, so Nov and Dec are left (2/5)
    pid = _plan(world)
    p = world.get("/api/installment-plans-progress").json()[pid]
    assert p == {
        "status": "terminando",
        "remaining": 2,
        "remaining_amount": "200.00",
        "next_n": 4,
        "next_month": "2026-11",
        "next_amount": "100.00",
        "installment_amount": "100.00",  # R14.21
    }


def test_r14_19_finished_plan_has_nothing_left(world: Api) -> None:
    pid = _plan(world, n=2, first="2026-01")
    p = world.get("/api/installment-plans-progress").json()[pid]
    assert (p["status"], p["remaining"], p["next_n"], p["next_month"]) == ("pago", 0, None, None)


def test_r14_19_month_items_say_which_installment_it_is(world: Api) -> None:
    _plan(world, n=10, first="2026-09")
    items = world.get("/api/reports/month-items", params={"month": "2026-12"}).json()
    [tv] = [i for i in items if i["description"] == "TV"]
    assert tv["installment"] == {"n": 4, "of": 10}
    assert tv["origin"] == "plan"


def test_r14_21_monthly_installment_with_cents_on_the_first(world: Api) -> None:
    r = world.post(
        "/api/installment-plans",
        {
            "card_id": "card_main",
            "description": "SOFA",
            "total_installments": 3,
            "first_invoice_month": "2026-11",
            "total_amount": "100.00",
            "category_id": "cat_food",
        },
    )
    p = world.get("/api/installment-plans-progress").json()[r.json()["id"]]
    # 100 / 3 = 33.33 per month; the cent left over goes to the 1st installment (33.34)
    assert (p["installment_amount"], p["next_amount"]) == ("33.33", "33.34")
