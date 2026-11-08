"""HTTP security controls (docs/13-seguranca.md "Controles").

- ``Host`` must be loopback (or an explicitly allowed name): blocks DNS rebinding.
- Mutating ``/api`` requests need ``X-Requested-With``: a cross-site form/fetch without CORS
  preflight cannot set it, so CSRF from another open tab is blocked.
- No CORS headers are ever emitted.
- Anti-clickjacking / sniffing headers on every response (X-Frame-Options, CSP frame-ancestors).
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DEFAULT_HOSTS = ("127.0.0.1", "localhost")
SECURITY_HEADERS = [
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (
        b"content-security-policy",
        b"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        b"frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    ),
]


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str] = DEFAULT_HOSTS) -> None:
        self.app = app
        self.allowed = {h.strip().lower() for h in allowed_hosts if h.strip()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "").lower()
        hostname = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        if hostname not in self.allowed:
            await _reject(send, 400, "invalid_host", "host not allowed")
            return
        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")
        if (
            path.startswith("/api")
            and method not in SAFE_METHODS
            and not headers.get("x-requested-with")
        ):
            await _reject(
                send,
                403,
                "csrf_header_missing",
                "mutating requests require the X-Requested-With header",
            )
            return

        async def send_with_headers(message: dict[str, object]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))  # type: ignore[call-overload]
                headers.extend(SECURITY_HEADERS)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)  # type: ignore[arg-type]


async def _reject(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message, "details": {}}}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
