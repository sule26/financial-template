"""HTTP layer: FastAPI application factory."""

from expense_tracker.api.app import create_app

__all__ = ["create_app"]
