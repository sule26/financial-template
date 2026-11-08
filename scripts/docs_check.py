#!/usr/bin/env python3
"""Check that every relative markdown link (file and #anchor) resolves.

Usage: python scripts/docs_check.py [ROOT]
Exit code 1 if any link is broken. Anchors follow GitHub slug rules.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "faturas", "extratos", "inbox", "data", "secrets", ".kiro",
             ".claude", "dist", "playwright-report", "test-results", ".venv"}
CODE_FENCE = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^#+\s+(.*)$", re.M)
LINK = re.compile(r"\]\(([^)\s]+)\)")


def slug(heading: str) -> str:
    text = re.sub(r"[`*]", "", heading.strip().lower())
    return "".join(c for c in text if c.isalnum() or c in "-_ ").replace(" ", "-")


def markdown_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        found.extend(Path(dirpath) / f for f in filenames if f.endswith(".md"))
    return sorted(found)


def check(root: Path) -> list[str]:
    files = markdown_files(root)
    anchors = {
        f.resolve(): {slug(h) for h in HEADING.findall(CODE_FENCE.sub("", f.read_text("utf-8")))}
        for f in files
    }
    problems: list[str] = []
    for f in files:
        body = CODE_FENCE.sub("", f.read_text("utf-8"))
        for link in LINK.findall(body):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, anchor = link.partition("#")
            target = (f.parent / path).resolve() if path else f.resolve()
            rel = f.relative_to(root)
            if not target.exists():
                problems.append(f"{rel}: missing file -> {link}")
            elif anchor and target.suffix == ".md":
                known = anchors.get(target)
                if known is None:
                    known = {slug(h) for h in HEADING.findall(CODE_FENCE.sub("", target.read_text("utf-8")))}
                if anchor not in known:
                    problems.append(f"{rel}: missing anchor -> {link}")
    return problems


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    problems = check(root)
    for p in problems:
        print(p)
    print(f"docs-check: {len(markdown_files(root))} files, {len(problems)} broken links")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
