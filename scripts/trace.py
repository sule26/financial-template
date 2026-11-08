#!/usr/bin/env python3
"""Requirement traceability (docs/10 Definition of Done).

For every task marked ``[x]`` in specs/expense-tracker-web/tasks.md, each requirement it cites
(``R3.4``, or ranges like ``R6.7–R6.12``, or whole groups like ``(R9)``) must have at least one
test whose name starts with ``test_r<major>_<minor>_`` anywhere under backend/tests or
frontend/src. Whole-group citations (``R9``) require at least one test for each requirement of
that group listed in requirements.md.

Usage: python scripts/trace.py [ROOT] [--all]
  --all  check every task, not only the completed ones (used by the final gate)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_LINE = re.compile(r"^- \[(?P<done>[ x])\] (?P<id>T\d+\.\d+)\b(?P<body>.*)$", re.M)
REQ_DEF = re.compile(r"^- (R(\d+)\.(\d+))\b", re.M)
RANGE = re.compile(r"R(\d+)\.(\d+)\s*[–-]\s*R?(?:(\d+)\.)?(\d+)")
SINGLE = re.compile(r"R(\d+)\.(\d+)")
GROUP = re.compile(r"(?<![\w.])R(\d+)(?![\d.])")
TEST_NAME = re.compile(r"\b(?:def|it|test)\s*\(?\s*['\"]?test_r(\d+)_(\d+)_", re.I)
TS_TEST = re.compile(r"""(?:it|test)\(\s*['"`]r(\d+)[._](\d+)\b""", re.I)


def defined_requirements(root: Path) -> dict[int, list[int]]:
    text = (root / "specs/expense-tracker-web/requirements.md").read_text("utf-8")
    groups: dict[int, list[int]] = {}
    for _, major, minor in REQ_DEF.findall(text):
        groups.setdefault(int(major), []).append(int(minor))
    return groups


def cited(body: str, groups: dict[int, list[int]]) -> set[tuple[int, int]]:
    refs: set[tuple[int, int]] = set()
    stripped = body
    for m in RANGE.finditer(body):
        major = int(m.group(1))
        end_major = int(m.group(3)) if m.group(3) else major
        if end_major == major:
            refs.update((major, n) for n in range(int(m.group(2)), int(m.group(4)) + 1))
        stripped = stripped.replace(m.group(0), " ")
    for m in SINGLE.finditer(stripped):
        refs.add((int(m.group(1)), int(m.group(2))))
    stripped = SINGLE.sub(" ", stripped)
    for m in GROUP.finditer(stripped):
        major = int(m.group(1))
        refs.update((major, n) for n in groups.get(major, []))
    return refs


def tested(root: Path) -> set[tuple[int, int]]:
    found: set[tuple[int, int]] = set()
    sources = list((root / "backend/tests").rglob("*.py"))
    frontend = root / "frontend/src"
    if frontend.is_dir():
        sources += [p for p in frontend.rglob("*.test.ts*") if "node_modules" not in p.parts]
    e2e = root / "frontend/e2e"
    if e2e.is_dir():
        sources += list(e2e.rglob("*.spec.ts"))
    for path in sources:
        text = path.read_text("utf-8")
        for pattern in (TEST_NAME, TS_TEST, re.compile(r"def test_r(\d+)_(\d+)_")):
            found.update((int(a), int(b)) for a, b in pattern.findall(text))
        # a test may cover several requirements: test_r8_6_r10_3_<behavior>
        for name in re.findall(r"def (test_(?:r\d+_\d+_)+)", text):
            found.update((int(a), int(b)) for a, b in re.findall(r"r(\d+)_(\d+)_", name))
    return found


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_all = "--all" in sys.argv
    root = Path(args[0] if args else ".").resolve()
    groups = defined_requirements(root)
    have = tested(root)
    tasks = (root / "specs/expense-tracker-web/tasks.md").read_text("utf-8")
    missing: list[str] = []
    checked = 0
    for m in TASK_LINE.finditer(tasks):
        if not check_all and m.group("done") != "x":
            continue
        checked += 1
        for major, minor in sorted(cited(m.group("body"), groups)):
            if minor in groups.get(major, []) and (major, minor) not in have:
                missing.append(f"{m.group('id')}: R{major}.{minor} has no test_r{major}_{minor}_*")
    for line in missing:
        print(line)
    total = sum(len(v) for v in groups.values())
    covered = sum(1 for major, minors in groups.items() for m in minors if (major, m) in have)
    print(f"trace: {checked} tasks checked, {covered} of {total} requirements have tests, "
          f"{len(missing)} missing")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
