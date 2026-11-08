"""Backward-compatible re-export: the parse result contract lives in the domain."""

from expense_tracker.domain.parse_result import ParseResult, RawLine

__all__ = ["ParseResult", "RawLine"]
