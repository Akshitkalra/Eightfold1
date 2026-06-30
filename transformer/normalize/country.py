"""Country normalization -> ISO-3166 alpha-2 (e.g. 'US', 'IN', 'GB').

Accepts country names, common variants, and existing alpha-2/alpha-3 codes.
Unknown input returns None.
"""
from __future__ import annotations

from typing import Optional

import pycountry

# Common informal variants that pycountry's fuzzy search may miss or mis-rank.
_ALIASES = {
    "usa": "US", "u.s.a.": "US", "u.s.": "US", "us": "US",
    "united states": "US", "united states of america": "US", "america": "US",
    "uk": "GB", "u.k.": "GB", "england": "GB", "britain": "GB",
    "great britain": "GB", "united kingdom": "GB",
    "uae": "AE", "south korea": "KR", "north korea": "KP",
    "russia": "RU", "bharat": "IN", "india": "IN",
}


def normalize_country(raw: Optional[str]) -> Optional[str]:
    """Return ISO-3166 alpha-2 code, or None if it cannot be resolved."""
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    key = s.lower().strip(". ")
    if key in _ALIASES:
        return _ALIASES[key]
    # Exact alpha-2
    if len(s) == 2:
        c = pycountry.countries.get(alpha_2=s.upper())
        if c:
            return c.alpha_2
    # Exact alpha-3
    if len(s) == 3:
        c = pycountry.countries.get(alpha_3=s.upper())
        if c:
            return c.alpha_2
    # Exact name
    c = pycountry.countries.get(name=s)
    if c:
        return c.alpha_2
    # Fuzzy fallback
    try:
        matches = pycountry.countries.search_fuzzy(s)
        if matches:
            return matches[0].alpha_2
    except LookupError:
        pass
    return None
