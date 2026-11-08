"""Bank profile schema, loader and detection (YAML profiles + optional Python plugins)."""

from expense_tracker.profiles.loader import (
    Plugin,
    ProfileSet,
    load_all,
    load_profiles,
    parse_profile,
)
from expense_tracker.profiles.schema import Profile

__all__ = ["Plugin", "Profile", "ProfileSet", "load_all", "load_profiles", "parse_profile"]
