"""Service errors and id generation."""

from __future__ import annotations

import secrets
import time
from typing import Any

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


class ServiceError(Exception):
    """Business error with a stable code; mapped to HTTP by the API layer."""

    status = 400

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class NotFound(ServiceError):
    status = 404


class Conflict(ServiceError):
    status = 409


class Invalid(ServiceError):
    status = 422


def new_id(prefix: str) -> str:
    """Prefix + sortable time component + random part (ULID-like, 26 chars)."""
    ms = int(time.time() * 1000)
    head = ""
    for _ in range(10):
        head = _ALPHABET[ms % 32] + head
        ms //= 32
    tail = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return f"{prefix}_{head}{tail}"
