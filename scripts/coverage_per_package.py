#!/usr/bin/env python3
"""Fail if any package under expense_tracker/ is below the coverage threshold.

Usage: python scripts/coverage_per_package.py coverage.json 90
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict


def main() -> int:
    path, threshold = sys.argv[1], float(sys.argv[2])
    data = json.load(open(path, encoding="utf-8"))
    stmts: dict[str, int] = defaultdict(int)
    covered: dict[str, int] = defaultdict(int)
    for filename, info in data["files"].items():
        parts = filename.replace("\\", "/").split("/")
        if "expense_tracker" not in parts:
            continue
        rest = parts[parts.index("expense_tracker") + 1 :]
        package = rest[0] if len(rest) > 1 else "(root)"
        summary = info["summary"]
        stmts[package] += summary["num_statements"] + summary.get("num_branches", 0)
        covered[package] += summary["covered_lines"] + summary.get("covered_branches", 0)
    failed = False
    for package in sorted(stmts):
        pct = 100.0 if stmts[package] == 0 else 100.0 * covered[package] / stmts[package]
        mark = "OK " if pct >= threshold else "LOW"
        failed |= pct < threshold
        print(f"{mark} {package:<12} {pct:6.2f}%")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
