"""Canonical data model.

Two record types:
  - RawRecord: loose, source-tagged output of an adapter (before merge).
  - CanonicalRecord: the clean, complete, merged profile (internal source of truth).

The projection layer (project.py) is the ONLY thing that reshapes a
CanonicalRecord for output. Everything upstream produces a full, consistent
CanonicalRecord so that downstream config changes never require engine changes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# --- Source trust ranking ---------------------------------------------------
# Higher = more trustworthy. Structured/recruiter-curated data outranks scraped
# free text. Documented and configurable; never random.
SOURCE_TRUST: dict[str, float] = {
    "ats_json": 0.95,
    "recruiter_csv": 0.90,
    "linkedin": 0.75,        # candidate-curated profile, fairly reliable
    "resume": 0.70,
    "recruiter_notes": 0.60,  # recruiter's free-text observations, subjective
    "github": 0.55,
}


def trust_weight(source: str) -> float:
    """Trust weight in [0,1] for a source name; unknown sources get a low default."""
    return SOURCE_TRUST.get(source, 0.40)


@dataclass
class RawRecord:
    """One candidate as seen by a single source, after extraction.

    Fields are intentionally loose/optional. `source` tags provenance so the
    merge step can rank conflicts and attribute every value.
    """

    source: str
    full_name: Optional[str] = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    location: dict[str, Optional[str]] = field(default_factory=dict)  # {city, region, country}
    links: dict[str, Any] = field(default_factory=dict)  # {linkedin, github, portfolio, other[]}
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[str] = field(default_factory=list)  # raw skill names (normalized later)
    experience: list[dict] = field(default_factory=list)  # {company,title,start,end,summary}
    education: list[dict] = field(default_factory=list)  # {institution,degree,field,end_year}


@dataclass
class SkillEntry:
    name: str
    confidence: float
    sources: list[str]


@dataclass
class Provenance:
    field: str
    source: str
    method: str  # direct | normalized | inferred | merged


@dataclass
class CanonicalRecord:
    """The clean, deduplicated, fully-traceable profile for one candidate."""

    candidate_id: str = ""
    full_name: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    location: dict[str, Optional[str]] = field(
        default_factory=lambda: {"city": None, "region": None, "country": None}
    )
    links: dict[str, Any] = field(
        default_factory=lambda: {"linkedin": None, "github": None, "portfolio": None, "other": []}
    )
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[SkillEntry] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    provenance: list[Provenance] = field(default_factory=list)
    overall_confidence: float = 0.0
    # internal: per-field confidence, not part of default output but used by projection
    field_confidence: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Full canonical dict (default output schema)."""
        d = asdict(self)
        # field_confidence is internal bookkeeping; keep out of the canonical dict
        d.pop("field_confidence", None)
        return d


def make_candidate_id(emails: list[str], phones: list[str], full_name: str) -> str:
    """Deterministic id from the strongest available identity key.

    Priority: email > phone > name. Same identity -> same id, always.
    """
    if emails:
        seed = "email:" + sorted(emails)[0]
    elif phones:
        seed = "phone:" + sorted(phones)[0]
    elif full_name:
        seed = "name:" + full_name.strip().lower()
    else:
        seed = "anon:"
    return "cand_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
