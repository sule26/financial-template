"""Catalog CRUD with referential integrity (docs/04 inv. 3 and 5) and category removal (R1.12)."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from expense_tracker.domain.allocation import AllocationError, resolve_card
from expense_tracker.domain.models import (
    Account,
    Allocation,
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
    SplitRef,
    Subscription,
    User,
)
from expense_tracker.domain.normalize import folder_name, strip_accents
from expense_tracker.services.errors import Conflict, Invalid, NotFound, new_id
from expense_tracker.storage import Repository

DEFAULT_CATEGORIES = [
    "Alimentação", "Aluguel", "Animais", "Banco", "Casa", "Compras", "Delivery", "Digital",
    "Educação", "Entretenimento", "Família", "Lazer", "Moradia", "Outros", "Pessoal", "Presente",
    "Saúde", "Trabalho", "Transporte",
]  # fmt: skip
# R14.24: what goes in each default category (shown next to the name when choosing one).
CATEGORY_HINTS: dict[str, str] = {
    "Alimentação": "Mercado, feira, padaria, açougue — comida para casa",
    "Aluguel": "Aluguel do imóvel e taxas do contrato",
    "Animais": "Ração, veterinário, banho e tosa, remédios do pet",
    "Banco": "Tarifas, anuidade, juros, IOF, encargos do cartão",
    "Casa": "Contas da casa: luz, água, gás, internet; móveis, eletrodomésticos, manutenção",
    "Compras": "Roupas, eletrônicos e compras em lojas que não são de outra categoria",
    "Delivery": "Pedidos por app (iFood, Rappi) e comida pronta entregue",
    "Digital": "Streaming, apps, jogos, assinaturas e serviços online",
    "Educação": "Escola, faculdade, cursos, livros e material",
    "Entretenimento": "Cinema, shows, eventos, ingressos",
    "Família": "Gastos com filhos, pais e parentes (mesada, ajuda, escola dos filhos)",
    "Lazer": "Restaurantes, bares, passeios, viagens",
    "Moradia": "Condomínio, IPTU, seguro residencial, financiamento do imóvel",
    "Outros": "O que não se encaixa em nenhuma outra",
    "Pessoal": "Cuidados pessoais: cabelo, cosméticos, academia",
    "Presente": "Presentes e doações",
    "Saúde": "Farmácia, consultas, exames, plano de saúde, dentista",
    "Trabalho": (
        "Gastos do trabalho (material, deslocamento a serviço) — muitas vezes reembolsáveis"
    ),
    "Transporte": (
        "Combustível, app de corrida, ônibus/metrô, estacionamento, pedágio, " "manutenção do carro"
    ),
}

PALETTE = ["#2F9E44", "#E8590C", "#7048E8", "#1971C2", "#C2255C", "#0C8599", "#F08C00",
           "#5C940D", "#9C36B5", "#3B5BDB", "#D9480F", "#099268", "#862E9C", "#868E96",
           "#1864AB", "#E64980", "#C92A2A", "#495057", "#0B7285"]  # fmt: skip

PREFIX = {
    "users": "usr",
    "split_profiles": "split",
    "accounts": "acc",
    "cards": "card",
    "categories": "cat",
    "savings_goals": "goal",
    "subscriptions": "sub",
    "recurring_purchases": "rec",
    "installment_plans": "plan",
    "rules": "rule",
    "settlements": "set",
    "investments": "inv",
    "benefits": "ben",
    "institutions": "inst",
}

MODELS: dict[str, type[BaseModel]] = {
    "users": User,
    "split_profiles": SplitProfile,
    "accounts": Account,
    "cards": Card,
    "categories": Category,
    "savings_goals": SavingsGoal,
    "subscriptions": Subscription,
    "recurring_purchases": RecurringPurchase,
    "installment_plans": InstallmentPlan,
    "rules": Rule,
    "settlements": Settlement,
    "investments": Investment,
    "benefits": Benefit,
    "institutions": Institution,
}


@dataclass
class Catalog:
    repo: Repository

    # ------------------------------------------------------------ helpers

    def _exists(self, name: str, key: str | None) -> bool:
        return key is None or self.repo.get(name, key) is not None

    def _need(self, name: str, key: str | None, field: str) -> None:
        if key is not None and self.repo.get(name, key) is None:
            raise Invalid(
                "reference_not_found", f"{field}: {key} does not exist", {"field": field, "id": key}
            )

    def check_allocation(self, spec: Allocation | None, field: str = "allocations") -> None:
        if spec is None:
            return
        if isinstance(spec, SplitRef):
            self._need("split_profiles", spec.split_id, f"{field}.split_id")
            return
        for share in spec:
            self._need("users", share.user_id, f"{field}.user_id")

    # ------------------------------------------------------------ validation per collection

    def validate(self, name: str, item: Any) -> None:
        check: Callable[[Any], None] | None = getattr(self, f"_check_{name}", None)
        if check is not None:
            check(item)
        # R14.27: every split of a split history must exist too
        for entry in getattr(item, "allocation_history", None) or []:
            self.check_allocation(entry.allocations, "allocation_history.allocations")

    def _check_users(self, item: User) -> None:
        collector = item.collector_user_id
        if collector is None:
            return
        if collector == item.id:
            raise Invalid(
                "invalid_collector",
                "collector_user_id: a user cannot pass on debts to themselves",
                {"field": "collector_user_id", "id": collector},
            )
        self._need("users", collector, "collector_user_id")

    def _check_split_profiles(self, item: SplitProfile) -> None:
        for m in item.members:
            self._need("users", m, "members")

    def _check_accounts(self, item: Account) -> None:
        self.check_allocation(item.owners, "owners")
        self.check_allocation(item.responsibles, "responsibles")
        self._need("users", item.responsible_user_id, "responsible_user_id")

    def _check_cards(self, item: Card) -> None:
        self.check_allocation(item.owners, "owners")
        self.check_allocation(item.responsibles, "responsibles")
        self._need("users", item.responsible_user_id, "responsible_user_id")
        self._need("accounts", item.account_id, "account_id")
        if item.parent_card_id is not None:
            if item.parent_card_id == item.id:
                raise Invalid("invalid_parent", "a card cannot be its own parent")
            parent = self.repo.get("cards", item.parent_card_id)
            if parent is None:
                raise Invalid("reference_not_found", f"parent_card_id: {item.parent_card_id}")
            if parent.parent_card_id is not None:
                raise Invalid("invalid_parent", "parent card must be a main card")
        cards = {c.id: c for c in self.repo.all("cards")}
        cards[item.id] = item
        accounts = {a.id: a for a in self.repo.all("accounts")}
        try:
            resolve_card(item, cards, accounts)
        except AllocationError as exc:
            raise Invalid("ownership_unresolved", str(exc)) from exc
        # every finals list must be unique across cards (identification in PDFs)
        for other in cards.values():
            if other.id != item.id and set(other.last_digits) & set(item.last_digits):
                raise Invalid(
                    "duplicate_last_digits", f"last digits already used by card {other.id}"
                )

    def _check_savings_goals(self, item: SavingsGoal) -> None:
        self._need("users", item.user_id, "user_id")

    def _owner_refs(self, item: Any) -> None:
        self._need("cards", getattr(item, "card_id", None), "card_id")
        self._need("accounts", getattr(item, "account_id", None), "account_id")
        self._need("categories", getattr(item, "category_id", None), "category_id")
        self.check_allocation(getattr(item, "allocations", None))

    def _check_subscriptions(self, item: Subscription) -> None:
        self._owner_refs(item)

    def _check_recurring_purchases(self, item: RecurringPurchase) -> None:
        self._owner_refs(item)

    def _check_installment_plans(self, item: InstallmentPlan) -> None:
        self._owner_refs(item)

    def _check_rules(self, item: Rule) -> None:
        import re

        if item.when.description_regex:
            try:
                re.compile(item.when.description_regex)
            except re.error as exc:
                raise Invalid("invalid_regex", f"description_regex: {exc}") from exc
        self._need("cards", item.when.card_id, "when.card_id")
        self._need("accounts", item.when.account_id, "when.account_id")
        self._need("categories", item.when.category_id, "when.category_id")
        self._need("categories", item.then.category_id, "then.category_id")
        self.check_allocation(item.then.allocations, "then.allocations")
        if item.then.category_id is None and item.then.allocations is None:
            raise Invalid("empty_rule", "rule must set a category and/or an allocation")

    def _check_settlements(self, item: Settlement) -> None:
        self._need("users", item.from_user_id, "from_user_id")
        self._need("users", item.to_user_id, "to_user_id")
        self._need("cards", item.card_id, "card_id")
        self._need("accounts", item.account_id, "account_id")

    def _prepare_settlements(self, item: Settlement) -> Settlement:
        """R13.16: a settlement linked to an additional card pays the main card's invoice."""
        if item.card_id is None:
            return item
        card = self.repo.get("cards", item.card_id)
        if card is None or card.parent_card_id is None:
            return item
        return item.model_copy(update={"card_id": card.parent_card_id})

    def _check_benefits(self, item: Benefit) -> None:
        self._need("users", item.user_id, "user_id")
        acc = self.repo.get("accounts", item.account_id)
        if acc is None:
            raise Invalid(
                "reference_not_found",
                f"account_id: {item.account_id} does not exist",
                {"field": "account_id", "id": item.account_id},
            )
        wanted = "benefit" if item.destination == "card" else "checking"
        if acc.type != wanted:
            raise Invalid(
                "benefit_account_type",
                "benefits on a card go to a benefit account (VR/VA card); benefits in an "
                "account go to a checking account",
            )

    def _check_investments(self, item: Investment) -> None:
        self.check_allocation(item.owners, "owners")
        self._need("savings_goals", item.goal_id, "goal_id")
        self._need("accounts", item.account_id, "account_id")
        ref = item.institution_id
        if ref is not None and not (
            self._exists("accounts", ref) or self._exists("institutions", ref)
        ):
            raise Invalid(
                "reference_not_found",
                f"institution_id: {ref} is neither an account nor an institution",
                {"field": "institution_id", "id": ref},
            )

    # ------------------------------------------------------------ CRUD

    def _prepare(self, name: str, item: Any) -> Any:
        prepare: Callable[[Any], Any] | None = getattr(self, f"_prepare_{name}", None)
        return item if prepare is None else prepare(item)

    def list_items(self, name: str) -> list[Any]:
        return self.repo.all(name)

    def get(self, name: str, key: str) -> Any:
        item = self.repo.get(name, key)
        if item is None:
            raise NotFound("not_found", f"{name}/{key} not found")
        return item

    def create(self, name: str, data: dict[str, Any]) -> Any:
        payload = dict(data)
        if not payload.get("id"):
            payload["id"] = new_id(PREFIX[name])
        elif self.repo.get(name, payload["id"]) is not None:
            raise Conflict("already_exists", f"{name}/{payload['id']} already exists")
        item = self._prepare(name, MODELS[name].model_validate(payload))
        self.validate(name, item)
        self.repo.put(name, item)
        return item

    def update(self, name: str, key: str, data: dict[str, Any]) -> Any:
        old = self.get(name, key)
        if name == "installment_plans" and old.origin.type == "import":
            # R14.20: a plan read from an invoice follows the bank; only my classification changes
            fixed = ("card_id", "total_amount", "total_installments", "first_invoice_month")
            new = MODELS[name].model_validate({**data, "id": key})
            changed = [f for f in fixed if getattr(new, f) != getattr(old, f)]
            if changed:
                raise Invalid(
                    "imported_readonly",
                    f"imported plan fields are read-only: {', '.join(changed)}",
                )
        payload = dict(data)
        payload["id"] = key
        item = self._prepare(name, MODELS[name].model_validate(payload))
        self.validate(name, item)
        self.repo.put(name, item)
        return item

    def delete(self, name: str, key: str) -> dict[str, Any]:
        self.get(name, key)
        if name == "categories":
            return self.delete_category(key)
        users = self._references(name, key)
        if users:
            raise Conflict(
                "in_use",
                f"{name}/{key} is referenced by {', '.join(users[:5])}",
                {"referenced_by": users},
            )
        self.repo.delete(name, key)
        return {"deleted": key}

    # ------------------------------------------------------------ references

    def _references(self, name: str, key: str) -> builtins.list[str]:
        refs: builtins.list[str] = []

        def alloc_uses(spec: Allocation | None) -> bool:
            if spec is None:
                return False
            if isinstance(spec, SplitRef):
                return name == "split_profiles" and spec.split_id == key
            return name == "users" and any(s.user_id == key for s in spec)

        def scan(coll: str, items: Iterable[Any], fields: dict[str, str]) -> None:
            for it in items:
                ident = getattr(it, "id", None) or getattr(it, "fingerprint", "?")
                for attr, target in fields.items():
                    if target == name and getattr(it, attr, None) == key:
                        refs.append(f"{coll}/{ident}")
                for attr in ("owners", "allocations", "responsibles"):
                    if alloc_uses(getattr(it, attr, None)):
                        refs.append(f"{coll}/{ident}")
                for entry in getattr(it, "allocation_history", None) or []:
                    if alloc_uses(entry.allocations):
                        refs.append(f"{coll}/{ident}")

        scan(
            "cards",
            self.repo.all("cards"),
            {"account_id": "accounts", "parent_card_id": "cards", "responsible_user_id": "users"},
        )
        scan("accounts", self.repo.all("accounts"), {"responsible_user_id": "users"})
        tx_fields = {"card_id": "cards", "account_id": "accounts"}
        scan("transactions", self.repo.all("transactions"), tx_fields)
        scan("staging", self.repo.all("staging"), tx_fields)
        owner_fields = {"card_id": "cards", "account_id": "accounts"}
        scan("subscriptions", self.repo.all("subscriptions"), owner_fields)
        scan("recurring_purchases", self.repo.all("recurring_purchases"), owner_fields)
        scan("installment_plans", self.repo.all("installment_plans"), {"card_id": "cards"})
        scan(
            "investments",
            self.repo.all("investments"),
            {"account_id": "accounts", "goal_id": "savings_goals"},
        )
        # R13.15: institution_id points to an account or to an institution
        scan("investments", self.repo.all("investments"), {"institution_id": "accounts"})
        scan("investments", self.repo.all("investments"), {"institution_id": "institutions"})
        scan(
            "settlements",
            self.repo.all("settlements"),
            {
                "from_user_id": "users",
                "to_user_id": "users",
                "card_id": "cards",
                "account_id": "accounts",
            },
        )
        scan("savings_goals", self.repo.all("savings_goals"), {"user_id": "users"})
        scan("users", self.repo.all("users"), {"collector_user_id": "users"})
        scan("benefits", self.repo.all("benefits"), {"user_id": "users", "account_id": "accounts"})
        for rule in self.repo.all("rules"):
            if alloc_uses(rule.then.allocations):
                refs.append(f"rules/{rule.id}")
            if name in ("cards", "accounts") and key in (rule.when.card_id, rule.when.account_id):
                refs.append(f"rules/{rule.id}")
        link_fields = {
            "subscription_id": "subscriptions",
            "recurring_purchase_id": "recurring_purchases",
            "investment_id": "investments",
            "settlement_id": "settlements",
        }
        for coll in ("transactions", "staging"):
            for tx in self.repo.all(coll):
                for attr, target in link_fields.items():
                    if target == name and getattr(tx.links, attr) == key:
                        refs.append(f"{coll}/{tx.id}")
                if name == "installment_plans" and tx.installment and tx.installment.plan_id == key:
                    refs.append(f"{coll}/{tx.id}")
        for ann in self.repo.all("annotations"):
            if alloc_uses(ann.allocations):
                refs.append(f"annotations/{ann.fingerprint}")
        if name == "users":
            for sp in self.repo.all("split_profiles"):
                if key in sp.members:
                    refs.append(f"split_profiles/{sp.id}")
        return sorted(set(refs))

    # ------------------------------------------------------------ categories (R1.11, R1.12)

    def delete_category(self, key: str) -> dict[str, Any]:
        """Remove a category even if in use: items become uncategorized (alert until fixed)."""
        affected: dict[str, int] = {}
        self.repo.backup(reason="delete-category")
        with self.repo.batch():
            for coll in (
                "transactions",
                "staging",
                "installment_plans",
                "subscriptions",
                "recurring_purchases",
                "annotations",
            ):
                count = 0
                for item in self.repo.all(coll):
                    if item.category_id == key:
                        self.repo.put(coll, item.model_copy(update={"category_id": None}))
                        count += 1
                if count:
                    affected[coll] = count
            rules = 0
            for rule in self.repo.all("rules"):
                changed = rule
                if rule.then.category_id == key:
                    changed = changed.model_copy(
                        update={"then": rule.then.model_copy(update={"category_id": None})}
                    )
                if rule.when.category_id == key:
                    changed = changed.model_copy(update={"enabled": False})
                if changed is not rule:
                    if changed.then.category_id is None and changed.then.allocations is None:
                        changed = changed.model_copy(update={"enabled": False})
                    self.repo.put("rules", changed)
                    rules += 1
            if rules:
                affected["rules"] = rules
            self.repo.delete("categories", key)
        return {"deleted": key, "uncategorized": affected}

    def seed_defaults(self) -> list[str]:
        """First run only (no categories file yet): create the standard category list.

        On later runs, a standard category (by name) without description gets the standard
        one (R14.24), so existing installs see what goes in each category too.
        """
        if self.repo.path("categories").exists() or self.repo.all("categories"):
            for cat in self.repo.all("categories"):
                hint = CATEGORY_HINTS.get(cat.name.strip())
                if hint and not cat.description:
                    self.repo.put("categories", cat.model_copy(update={"description": hint}))
            return []
        created = []
        for i, name in enumerate(DEFAULT_CATEGORIES):
            color = PALETTE[i % len(PALETTE)]
            cid = "cat_" + folder_name(name).replace(" ", "_")
            self.repo.put(
                "categories",
                Category(
                    id=strip_accents(cid),
                    name=name,
                    color=color,
                    description=CATEGORY_HINTS.get(name),
                ),
            )
            created.append(name)
        return created

    def uncategorized(self) -> dict[str, builtins.list[str]]:
        """Items without category (R1.12 alert)."""
        out: dict[str, builtins.list[str]] = {}
        for coll in ("transactions", "installment_plans", "subscriptions", "recurring_purchases"):
            ids = [
                i.id
                for i in self.repo.all(coll)
                if i.category_id is None
                and getattr(i, "kind", "expense") in ("expense", "refund", "fee", "investment")
            ]
            if ids:
                out[coll] = ids
        return out
