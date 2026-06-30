"""Skill canonicalization.

Maps aliases/casing/punctuation variants to a single canonical skill name using
data/skills_canonical.json. Unknown skills are kept verbatim (title-trimmed) so
we never drop real signal -- they just won't get an alias boost, and the merge
step assigns them lower confidence.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "skills_canonical.json"


@lru_cache(maxsize=1)
def _alias_map() -> dict[str, str]:
    with open(_DATA, "r", encoding="utf-8") as f:
        return {k.lower(): v for k, v in json.load(f).items()}


def _key(raw: str) -> str:
    # collapse whitespace, lowercase, strip surrounding punctuation
    return re.sub(r"\s+", " ", raw.strip().lower()).strip(" .,-")


def canonical_skill(raw: Optional[str]) -> Optional[str]:
    """Canonical name for one skill, or None for empty input.

    Known alias -> canonical; unknown -> cleaned verbatim (preserve signal).
    """
    if not raw or not str(raw).strip():
        return None
    k = _key(str(raw))
    if not k:
        return None
    mapped = _alias_map().get(k)
    if mapped:
        return mapped
    # unknown skill: return a tidied version of the original
    return str(raw).strip()


def canonical_skills(raws: list[str]) -> list[str]:
    """Canonicalize a list, dedupe case-insensitively, order-stable."""
    out: list[str] = []
    seen: set[str] = set()
    for r in raws:
        c = canonical_skill(r)
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def is_known(raw: str) -> bool:
    """True if the skill maps to a curated canonical name (used for confidence)."""
    return _key(str(raw)) in _alias_map()


def scan_skills(text: str) -> list[str]:
    """Find curated skills mentioned anywhere in free text (recruiter notes).

    Only curated aliases are detected -- we never guess a skill from arbitrary
    words. Matches are bounded by non-alphanumeric chars so 'go' won't fire
    inside 'good' but 'C++' still matches.
    """
    if not text:
        return []
    low = text.lower()
    out: list[str] = []
    for alias, canon in _alias_map().items():
        pat = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
        if re.search(pat, low) and canon not in out:
            out.append(canon)
    return out
