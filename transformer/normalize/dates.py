"""Date normalization.

  - to_year_month: -> 'YYYY-MM' (experience start/end)
  - to_year:       -> 'YYYY'    (education end_year)
  - 'present'/'current'/'now' -> None end (still ongoing)

Unparseable input returns None. We never fabricate a date.
"""
from __future__ import annotations

import re
from typing import Optional

from dateutil import parser as dtparser

_PRESENT = {"present", "current", "now", "ongoing", "till date", "to date"}


def _clean(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def to_year_month(raw: Optional[str]) -> Optional[str]:
    """Parse many date shapes into 'YYYY-MM'. Returns None if unparseable/present."""
    s = _clean(raw)
    if s is None or s.lower() in _PRESENT:
        return None
    # Already YYYY-MM or YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    # Bare year
    if re.fullmatch(r"\d{4}", s):
        return f"{s}-01"
    try:
        dt = dtparser.parse(s, default=dtparser.parse("2000-01-01"))
        return f"{dt.year:04d}-{dt.month:02d}"
    except (ValueError, OverflowError):
        return None


def to_year(raw: Optional[str]) -> Optional[str]:
    """Parse into a 4-digit 'YYYY'. Returns None if unparseable/present."""
    s = _clean(raw)
    if s is None or s.lower() in _PRESENT:
        return None
    m = re.search(r"(19|20)\d{2}", s)
    if m:
        return m.group(0)
    try:
        dt = dtparser.parse(s)
        return f"{dt.year:04d}"
    except (ValueError, OverflowError):
        return None
