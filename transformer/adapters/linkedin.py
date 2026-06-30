"""LinkedIn adapter (unstructured source).

Live scraping of LinkedIn is auth-walled and against their ToS, so we do NOT
fetch profiles over the network. Instead this adapter accepts what you can
legitimately obtain:

  1. A profile URL  -> contributes the canonical linkedin link only (no invented
     fields). The link still helps merge/dedup across sources.
  2. A saved/exported profile as JSON -> name, headline, location, skills,
     experience, education.
  3. A saved profile as plain text -> parsed with the resume section heuristics,
     re-tagged as the linkedin source.

`parse_input` dispatches on whichever form it's given.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from ..canonical import RawRecord
from . import resume_text

_URL_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)", re.I)


def _is_url(value: str) -> bool:
    return bool(_URL_RE.search(value or ""))


def _canonical_url(value: str) -> Optional[str]:
    m = _URL_RE.search(value or "")
    return f"https://linkedin.com/in/{m.group(1)}" if m else None


def parse_url(url: str) -> list[RawRecord]:
    """A bare profile URL -> just the link (we don't scrape)."""
    canon = _canonical_url(url)
    if not canon:
        return []
    return [RawRecord(source="linkedin", links={"linkedin": canon})]


def parse_json(text: str) -> list[RawRecord]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    blobs = data if isinstance(data, list) else [data]
    out: list[RawRecord] = []
    for b in blobs:
        if isinstance(b, dict):
            rec = _blob_to_record(b)
            if rec is not None:
                out.append(rec)
    return out


def _g(d: dict, *keys) -> Optional[Any]:
    lower = {k.lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, "", [], {}):
            return v
    return None


def _blob_to_record(b: dict) -> RawRecord | None:
    rec = RawRecord(source="linkedin")
    rec.full_name = _s(_g(b, "name", "full_name", "fullName"))
    rec.headline = _s(_g(b, "headline", "title", "summary"))

    email = _g(b, "email", "emailAddress")
    if email:
        rec.emails = [str(email)]

    loc = _g(b, "location", "geo")
    if isinstance(loc, dict):
        rec.location = {"city": _s(_g(loc, "city")), "region": _s(_g(loc, "region", "state")),
                        "country": _s(_g(loc, "country"))}
    elif isinstance(loc, str):
        rec.location = {"city": loc, "region": None, "country": loc}

    skills = _g(b, "skills", "skill_set")
    if isinstance(skills, list):
        rec.skills = [str(s) for s in skills if str(s).strip()]

    url = _g(b, "url", "profile_url", "linkedin", "publicProfileUrl")
    canon = _canonical_url(str(url)) if url else None
    if canon:
        rec.links = {"linkedin": canon}

    for e in _g(b, "experience", "positions", "work_history") or []:
        if isinstance(e, dict):
            rec.experience.append({
                "company": _s(_g(e, "company", "companyName", "employer")),
                "title": _s(_g(e, "title", "role", "position")),
                "start": _s(_g(e, "start", "start_date", "from", "startDate")),
                "end": _s(_g(e, "end", "end_date", "to", "endDate")),
                "summary": _s(_g(e, "summary", "description")),
            })
    for e in _g(b, "education", "schools") or []:
        if isinstance(e, dict):
            rec.education.append({
                "institution": _s(_g(e, "school", "institution", "schoolName", "university")),
                "degree": _s(_g(e, "degree", "degreeName")),
                "field": _s(_g(e, "field", "fieldOfStudy", "major")),
                "end_year": _s(_g(e, "end_year", "endYear", "graduation_year", "year", "end")),
            })

    if not any([rec.full_name, rec.emails, rec.skills, rec.experience, rec.links]):
        return None
    return rec


def _s(v: Any) -> Optional[str]:
    if v in (None, "", [], {}):
        return None
    return str(v)


def parse_file(path: str) -> list[RawRecord]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if p.suffix.lower() == ".json" or text.lstrip().startswith(("{", "[")):
        return parse_json(text)
    # plain-text profile: reuse resume heuristics but tag as linkedin
    recs = resume_text.parse(text)
    for r in recs:
        r.source = "linkedin"
    return recs


def parse_input(value: str) -> list[RawRecord]:
    """Dispatch a CLI/UI value: URL, file path, or inline JSON/text."""
    if not value or not str(value).strip():
        return []
    value = str(value).strip()
    if Path(value).exists():
        return parse_file(value)
    # Check JSON before URL: an exported profile is JSON that *contains* a
    # linkedin URL, so the URL test would otherwise misroute it.
    if value.startswith(("{", "[")):
        return parse_json(value)
    if _is_url(value):
        return parse_url(value)
    return []
