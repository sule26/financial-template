"""Text normalization and similarity (docs/04 "Fingerprint", docs/09 "Descrição similar")."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

INSTALLMENT_SUFFIXES = [
    re.compile(r"\s*\(?parcela\s+\d{1,2}\s*(?:de|/)\s*\d{1,2}\)?\s*$", re.I),
    re.compile(r"\s*-?\s*parcela\s+\d{1,2}\s*/\s*\d{1,2}\s*$", re.I),
    re.compile(r"\s+\d{1,2}/\d{1,2}\s*$"),
]
ANTICIPATION_PREFIX = re.compile(r"^antecipad[ao]\s*-\s*", re.I)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_description(text: str) -> str:
    """Uppercase, no accents, collapsed spaces, without the installment suffix."""
    value = text.strip()
    for pattern in INSTALLMENT_SUFFIXES:
        value = pattern.sub("", value)
    value = ANTICIPATION_PREFIX.sub("", value)
    value = strip_accents(value).upper()
    value = re.sub(r"[^\w*/.\- ]", " ", value)
    return re.sub(r"\s+", " ", value).strip(" -")


def folder_key(name: str) -> str:
    """Key to match an inbox folder with a card/account name ("Mercado Pago" == "mercado-pago")."""
    return re.sub(r"[\s_\-]+", " ", strip_accents(name).lower()).strip()


def folder_name(name: str) -> str:
    """Folder created for a card/account: the same name, all lowercase (operator's choice)."""
    cleaned = re.sub(r"[/\\\x00]", " ", name).strip().lower()
    return re.sub(r"\s+", " ", cleaned) or "sem-nome"


def similarity(a: str, b: str) -> float:
    """``difflib`` ratio over normalized descriptions."""
    na, nb = normalize_description(a), normalize_description(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()
