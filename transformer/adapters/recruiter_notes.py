"""Recruiter notes adapter (unstructured source).

Free-text notes a recruiter jots down after a call, e.g.:

    Spoke with Robert Smith today. ~8 yrs experience, currently Staff Eng at
    Acme. Strong in Python, AWS, Kubernetes. Based in San Francisco. Reach him
    at bob.smith@example.com / (415) 555-0100.

We extract only what we can see explicitly -- emails, phones, curated skills,
and a labelled name ("Name: ..." or "Spoke with <Name>") -- and keep the raw
note as the headline. Everything else is left null; we never infer. Low trust
(recruiter_notes) because notes are subjective and abbreviated.
"""
from __future__ import annotations

import re
from typing import Optional

from ..canonical import RawRecord
from ..normalize.emails import extract_emails
from ..normalize.skills import scan_skills

_PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{7,}\d)")
# "Name: Robert Smith" | "Candidate: Robert Smith" | "Spoke with Robert Smith".
# The name token excludes '.' so it stops at a sentence boundary (won't run into
# the next sentence), while still allowing hyphens/apostrophes (O'Brien, Anne-Marie).
_NAME_TOKEN = r"[A-Z][a-zA-Z''\-]+(?:\s+[A-Z][a-zA-Z''\-]+){1,3}"
_NAME_RE = re.compile(
    r"(?i:name|candidate)\s*[:\-]\s*(" + _NAME_TOKEN + r")"
    r"|(?i:spoke)\s+(?i:with|to)\s+(" + _NAME_TOKEN + r")",
)


def parse(text: str) -> list[RawRecord]:
    if not text or not text.strip():
        return []
    rec = RawRecord(source="recruiter_notes")
    rec.emails = extract_emails(text)
    rec.phones = [m.group(1).strip() for m in _PHONE_RE.finditer(text)]
    rec.skills = scan_skills(text)
    rec.full_name = _name(text)

    summary = re.sub(r"\s+", " ", text).strip()
    if summary:
        rec.headline = summary[:200]

    if not any([rec.full_name, rec.emails, rec.phones, rec.skills]):
        return []
    return [rec]


def _name(text: str) -> Optional[str]:
    m = _NAME_RE.search(text)
    if not m:
        return None
    name = m.group(1) or m.group(2)
    return re.sub(r"\s+", " ", name).strip() if name else None


def parse_file(path: str) -> list[RawRecord]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return parse(f.read())
    except OSError:
        return []
