"""Uvicorn entrypoint: ``python -m expense_tracker``."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from expense_tracker.api.app import create_app


def main() -> None:  # pragma: no cover - process entrypoint
    static = Path(os.environ.get("STATIC_DIR", "/app/static"))
    app = create_app(static_dir=static)
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        workers=1,
        access_log=False,  # docs/13: query strings carry descriptions and amounts
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
