"""Load bank profiles (YAML) and optional Python plugins (docs/06 "Plugin Python")."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import ValidationError

from expense_tracker.profiles.schema import Profile


class Plugin(Protocol):
    """Escape hatch for layouts that regex cannot handle."""

    id: str
    kind: str

    def detect(self, text: str) -> bool: ...

    def parse(self, pages: list[str]) -> Any: ...


@dataclass
class ProfileSet:
    profiles: dict[str, Profile] = field(default_factory=dict)
    plugins: dict[str, Plugin] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)  # file name -> message
    sources: dict[str, str] = field(default_factory=dict)  # profile id -> file name


def parse_profile(text: str) -> Profile:
    """Validate a profile YAML document; raises ``ValueError`` with a readable message."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("profile must be a YAML mapping")
    try:
        return Profile.model_validate(data)
    except ValidationError as exc:
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
        raise ValueError("; ".join(parts)) from exc


def load_all(directory: Path, examples: Path | None) -> ProfileSet:
    """User profiles (``profiles/``) plus the built-in examples for ids not overridden.

    The examples make the supported banks (Inter, Nubank) work out of the box; a user profile
    with the same id always wins.
    """
    result = load_profiles(directory)
    if examples is not None and examples.is_dir() and examples.resolve() != directory.resolve():
        builtin = load_profiles(examples)
        for pid, profile in builtin.profiles.items():
            if pid not in result.profiles and pid not in result.plugins:
                result.profiles[pid] = profile
                result.sources[pid] = f"(exemplo) {builtin.sources[pid]}"
    return result


def load_profiles(directory: Path) -> ProfileSet:
    """Load ``*.yaml`` in ``directory`` and ``plugins/*.py``. Errors are collected.

    R14.35: ``.yml`` is no longer read; such a file is reported so it can be renamed.
    """
    result = ProfileSet()
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.yml")):
        result.errors[path.name] = f"extensão .yml não é mais lida: renomeie para {path.stem}.yaml"
    for path in sorted(directory.glob("*.yaml")):
        try:
            profile = parse_profile(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            result.errors[path.name] = str(exc)
            continue
        if profile.id in result.profiles:
            result.errors[path.name] = f"duplicated profile id {profile.id!r}"
            continue
        result.profiles[profile.id] = profile
        result.sources[profile.id] = path.name
    plugins = directory / "plugins"
    if plugins.is_dir():
        for path in sorted(plugins.glob("*.py")):
            try:
                plugin = _load_plugin(path)
            except Exception as exc:  # plugin code is user code: never crash the app
                result.errors[f"plugins/{path.name}"] = f"{type(exc).__name__}: {exc}"
                continue
            if plugin.id in result.profiles or plugin.id in result.plugins:
                result.errors[f"plugins/{path.name}"] = f"duplicated profile id {plugin.id!r}"
                continue
            result.plugins[plugin.id] = plugin
            result.sources[plugin.id] = f"plugins/{path.name}"
    return result


def _load_plugin(path: Path) -> Plugin:
    spec = importlib.util.spec_from_file_location(f"et_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parser_cls = getattr(module, "Parser", None)
    if parser_cls is None:
        raise ImportError("plugin must define a class named Parser")
    plugin: Plugin = parser_cls()
    for attr in ("id", "kind", "detect", "parse"):
        if not hasattr(plugin, attr):
            raise ImportError(f"Parser is missing {attr!r}")
    if plugin.kind not in ("fatura", "extrato"):
        raise ImportError("Parser.kind must be 'fatura' or 'extrato'")
    return plugin
