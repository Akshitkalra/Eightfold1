"""Phone normalization -> E.164 (e.g. +14155550100).

Unparseable input returns None (we never guess a number).
"""
from __future__ import annotations

from typing import Optional

import phonenumbers


def normalize_phone(raw: Optional[str], default_region: str = "US") -> Optional[str]:
    """Return E.164 string, or None if it cannot be parsed as a valid number.

    default_region is used only when the input has no country code (e.g. a bare
    US 10-digit number). Numbers that are clearly invalid return None rather
    than an invented value.
    """
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    try:
        # If it already starts with '+', region is ignored by the parser.
        num = phonenumbers.parse(text, None if text.startswith("+") else default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def normalize_phones(raws: list[str], default_region: str = "US") -> list[str]:
    """Normalize a list of phones, dropping unparseable ones, deduped, order-stable."""
    seen: list[str] = []
    for r in raws:
        e164 = normalize_phone(r, default_region)
        if e164 and e164 not in seen:
            seen.append(e164)
    return seen
