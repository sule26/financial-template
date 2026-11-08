#!/usr/bin/env python3
"""Generate synthetic files for the e2e test (no personal data).

Usage: python scripts/e2e_fixtures.py OUT_DIR
Writes OUT_DIR/inter.pdf with an Inter-like invoice due on the 15th of the current month, so the
app (which always opens on the real current month) shows it on the Summary.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "tests"))

from fixtures.files import Line, inter_invoice, write  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1])
    today = date.today()
    prev_month = today.month - 1 or 12
    prev_year = today.year if today.month > 1 else today.year - 1
    due = f"15/{today.month:02d}/{today.year}"
    lines = [
        Line(10, prev_month, prev_year, "MERCADO BOM", "200.00", "1234"),
        Line(12, prev_month, prev_year, "FARMACIA BEM", "80.00", "1234"),
    ]
    write(out / "inter.pdf", inter_invoice(lines, due=due, main_card="1234"))
    print(f"e2e fixtures written to {out} (due {due})")


if __name__ == "__main__":
    main()
