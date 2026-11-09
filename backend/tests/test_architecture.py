"""Architecture tests: module dependency direction and domain purity (docs/03, docs/11)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "expense_tracker"

# docs/03-arquitetura.md#camadas-e-dependências-permitidas
FORBIDDEN: dict[str, set[str]] = {
    "domain": {"storage", "profiles", "importing", "review", "sync", "api", "config"},
    "storage": {"api", "sync", "review", "importing", "profiles"},
    "profiles": {"storage", "api", "review", "sync", "importing"},
    "importing": {"storage", "api", "review", "sync"},
    "review": {"api", "sync", "importing"},
    "sync": {"api"},
    "services": {"api", "sync", "importing", "review"},
}

DOMAIN_FORBIDDEN_MODULES = {"os", "pathlib", "shutil", "io", "subprocess", "socket", "fcntl"}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def _package_files(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_layer_dependencies(package: str) -> None:
    violations = []
    for file in _package_files(package):
        for name in _imports(file):
            parts = name.split(".")
            if parts[0] == "expense_tracker" and len(parts) > 1 and parts[1] in FORBIDDEN[package]:
                violations.append(f"{file.relative_to(SRC)} imports {name}")
    assert not violations, "\n".join(violations)


def test_domain_has_no_io() -> None:
    violations = []
    for file in _package_files("domain"):
        source = file.read_text(encoding="utf-8")
        for name in _imports(file):
            if name.split(".")[0] in DOMAIN_FORBIDDEN_MODULES:
                violations.append(f"{file.relative_to(SRC)} imports {name}")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    violations.append(f"{file.relative_to(SRC)} calls open()")
                if isinstance(func, ast.Attribute) and func.attr in {"now", "today", "utcnow"}:
                    base = func.value
                    if isinstance(base, ast.Name) and base.id in {"datetime", "date"}:
                        violations.append(f"{file.relative_to(SRC)} calls {base.id}.{func.attr}()")
    assert not violations, "\n".join(violations)


def test_all_packages_exist() -> None:
    for package in FORBIDDEN:
        assert (SRC / package / "__init__.py").is_file(), package


# R14.35: configuration files use ".yaml", never ".yml" (docs/12 "Arquivos YAML")
REPO = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {".git", "node_modules", "data", "inbox", "secrets", "faturas", ".hypothesis"}


def test_r14_35_no_yml_files_in_the_repo() -> None:
    found = [
        str(p.relative_to(REPO))
        for p in REPO.rglob("*.yml")
        if not _SKIP_DIRS & set(p.relative_to(REPO).parts)
    ]
    assert found == [], f"rename to .yaml: {found}"
    assert (REPO / "Taskfile.yaml").is_file()
    assert (REPO / "compose.yaml").is_file()
