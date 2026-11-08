"""Request-scoped access to services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Request

from expense_tracker.clock import Clock
from expense_tracker.config import Settings
from expense_tracker.services.catalog import Catalog
from expense_tracker.services.reports import Reports
from expense_tracker.services.transactions import Transactions
from expense_tracker.storage import Repository


@dataclass
class AppContext:
    settings: Settings
    clock: Clock
    repo: Repository
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def catalog(self) -> Catalog:
        return Catalog(self.repo)

    @property
    def reports(self) -> Reports:
        return Reports(self.repo, self.clock.today())

    @property
    def transactions(self) -> Transactions:
        hook = self.extras.get("after_manual_change")
        return Transactions(self.repo, self.clock.today(), self.clock.now, hook)


def ctx(request: Request) -> AppContext:
    context: AppContext = request.app.state.ctx
    return context
