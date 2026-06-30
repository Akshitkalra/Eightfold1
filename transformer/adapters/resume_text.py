"""Resume adapter (unstructured source).

Parses free-text resumes (.txt; .pdf if pdfplumber is installed) using
section-header heuristics + light regex. This is intentionally rule-based and
explainable -- no ML, no guessing. Anything we can't confidently extract is
simply left out (becomes null downstream), never invented.

Extracts: name (first non-empty line heuristic), emails, phones, a SKILLS
section, EXPERIENCE entries, and EDUCATION entries.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..canonical import RawRecord
from ..normalize.emails import extract_emails

# Section headers we recognize (case-insensitive, line-anchored).
_SECTIONS = {
    "skills": re.compile(r"^\s*(technical\s+)?skills?\s*:?\s*$", re.I),
    "experience": re.compile(r"^\s*(work\s+)?(experience|employment|history)\s*:?\s*$", re.I),
    "education": re.compile(r"^\s*education\s*:?\s*$", re.I),
    "summary": re.compile(r"^\s*(summary|objective|profile|about)\s*:?\s*$", re.I),
}

_PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{7,}\d)")
_DATE_RANGE = re.compile(
    r"(?P<start>[A-Za-z]{3,9}\.?\s*\d{4}|\d{1,2}/\d{4}|\d{4})\s*[-–—to]+\s*"
    r"(?P<end>present|current|now|[A-Za-z]{3,9}\.?\s*\d{4}|\d{1,2}/\d{4}|\d{4})",
    re.I,
)
_YEAR_RE = re.compile(r"(19|20)\d{2}")


def parse(text: str) -> list[RawRecord]:
    if not text or not text.strip():
        return []
    lines = [ln.rstrip() for ln in text.splitlines()]
    rec = RawRecord(source="resume")

    rec.emails = extract_emails(text)
    rec.phones = _phones(text)
    rec.full_name = _guess_name(lines)

    sections = _split_sections(lines)
    if sections.get("skills"):
        rec.skills = _parse_skills(sections["skills"])
    if sections.get("summary"):
        summary = " ".join(s.strip() for s in sections["summary"] if s.strip())
        if summary:
            rec.headline = summary[:200]
    if sections.get("experience"):
        rec.experience = _parse_experience(sections["experience"])
    if sections.get("education"):
        rec.education = _parse_education(sections["education"])

    if not any([rec.full_name, rec.emails, rec.phones, rec.skills, rec.experience]):
        return []
    return [rec]


def _phones(text: str) -> list[str]:
    # Return raw candidate phone strings; normalization happens in merge.
    return [m.group(1).strip() for m in _PHONE_RE.finditer(text)]


def _guess_name(lines: list[str]) -> Optional[str]:
    """Heuristic: first non-empty line that looks like a name (2-4 capitalized words,
    no '@', no digits). Resumes almost always lead with the name."""
    for ln in lines[:8]:
        s = ln.strip()
        if not s or "@" in s or any(ch.isdigit() for ch in s):
            continue
        words = s.split()
        if 2 <= len(words) <= 4 and all(w[:1].isupper() for w in words if w):
            return s
    return None


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Bucket lines under the most recent recognized section header."""
    out: dict[str, list[str]] = {}
    current: Optional[str] = None
    for ln in lines:
        header = None
        for name, rx in _SECTIONS.items():
            if rx.match(ln):
                header = name
                break
        if header:
            current = header
            out.setdefault(current, [])
            continue
        if current:
            out[current].append(ln)
    return out


def _parse_skills(block: list[str]) -> list[str]:
    raw = " ".join(block)
    parts = re.split(r"[,;|/•·•]| {2,}", raw)
    return [p.strip() for p in parts if p.strip()]


def _parse_experience(block: list[str]) -> list[dict]:
    entries: list[dict] = []
    for ln in block:
        s = ln.strip()
        if not s:
            continue
        m = _DATE_RANGE.search(s)
        if m:
            # Text before the date range is usually "Title, Company" or "Title at Company".
            head = s[: m.start()].strip(" -–—,|")
            title, company = _split_title_company(head)
            entries.append({
                "company": company,
                "title": title,
                "start": m.group("start"),
                "end": m.group("end"),
                "summary": None,
            })
        elif entries and s.startswith(("-", "*", "•")):
            # bullet -> append to previous entry's summary
            prev = entries[-1]
            bullet = s.lstrip("-*• ").strip()
            prev["summary"] = (prev["summary"] + " " if prev["summary"] else "") + bullet
    return entries


def _split_title_company(head: str) -> tuple[Optional[str], Optional[str]]:
    if not head:
        return None, None
    for sep in [" at ", " @ ", ", ", " - ", " — "]:
        if sep in head:
            left, right = head.split(sep, 1)
            return left.strip() or None, right.strip() or None
    return head.strip() or None, None


def _parse_education(block: list[str]) -> list[dict]:
    entries: list[dict] = []
    for ln in block:
        s = ln.strip()
        if not s:
            continue
        year = None
        ym = _YEAR_RE.search(s)
        if ym:
            year = ym.group(0)
        # Heuristic: "Degree, Institution" or "Institution — Degree"
        degree = institution = None
        m = re.search(r"(B\.?\s?Tech|B\.?\s?E\.?|B\.?\s?Sc|B\.?\s?S\.?|M\.?\s?Tech|"
                      r"M\.?\s?Sc|M\.?\s?S\.?|MBA|Bachelor[s']?|Master[s']?|Ph\.?D)"
                      r"[^,;\n]*", s, re.I)
        if m:
            degree = m.group(0).strip()
        parts = re.split(r"[,|—–-]", s)
        for p in parts:
            p = p.strip()
            if re.search(r"university|college|institute|school|iit|nit", p, re.I):
                institution = p
                break
        if degree or institution:
            entries.append({
                "institution": institution,
                "degree": degree,
                "field": None,
                "end_year": year,
            })
    return entries


def parse_file(path: str) -> list[RawRecord]:
    p = Path(path)
    try:
        if p.suffix.lower() == ".pdf":
            return _parse_pdf(p)
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return parse(f.read())
    except OSError:
        return []


def _parse_pdf(path: Path) -> list[RawRecord]:
    try:
        import pdfplumber  # optional dependency
    except ImportError:
        return []
    try:
        with pdfplumber.open(str(path)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return parse(text)
    except Exception:
        return []
