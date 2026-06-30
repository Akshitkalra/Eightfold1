"""Merge engine: normalize -> cluster -> resolve conflicts -> score.

Turns many source-tagged RawRecords into a list of clean CanonicalRecords, one
per real person. Every populated field carries provenance {field, source,
method} and a confidence score. Deterministic: no randomness anywhere.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .canonical import (
    CanonicalRecord,
    Provenance,
    RawRecord,
    SkillEntry,
    make_candidate_id,
    trust_weight,
)
from .confidence import field_confidence, overall_confidence
from .normalize.country import normalize_country
from .normalize.dates import to_year, to_year_month
from .normalize.emails import normalize_emails
from .normalize.phones import normalize_phones
from .normalize.skills import canonical_skill, canonical_skills, is_known


# --- Normalized intermediate representation ---------------------------------
@dataclass
class NormRecord:
    """A RawRecord with all values normalized, source tag preserved."""

    source: str
    full_name: Optional[str] = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    location: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    headline: Optional[str] = None
    years_experience: Optional[float] = None
    skills: list[str] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)


def normalize_record(raw: RawRecord) -> NormRecord:
    n = NormRecord(source=raw.source)
    n.full_name = _clean_name(raw.full_name)
    n.emails = normalize_emails(raw.emails)
    n.phones = normalize_phones(raw.phones)
    n.headline = (raw.headline or "").strip() or None
    n.years_experience = raw.years_experience
    n.skills = canonical_skills(raw.skills)

    if raw.location:
        city = (raw.location.get("city") or "").strip() or None
        region = (raw.location.get("region") or "").strip() or None
        country = normalize_country(raw.location.get("country"))
        # If 'city' actually held a country-ish string and we got a country, blank the city.
        if city and normalize_country(city) == country and country:
            city = None
        n.location = {"city": city, "region": region, "country": country}

    n.links = {k: v for k, v in (raw.links or {}).items() if v}

    for e in raw.experience:
        n.experience.append({
            "company": _clean(e.get("company")),
            "title": _clean(e.get("title")),
            "start": to_year_month(e.get("start")),
            "end": to_year_month(e.get("end")),
            "summary": _clean(e.get("summary")),
        })
    for e in raw.education:
        n.education.append({
            "institution": _clean(e.get("institution")),
            "degree": _clean(e.get("degree")),
            "field": _clean(e.get("field")),
            "end_year": to_year(e.get("end_year")),
        })
    return n


def _clean(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _clean_name(v) -> Optional[str]:
    s = _clean(v)
    if not s:
        return None
    return re.sub(r"\s+", " ", s)


# --- Clustering (union-find over match keys) --------------------------------
def _match_keys(n: NormRecord) -> set[str]:
    keys: set[str] = set()
    for e in n.emails:
        keys.add(f"email:{e}")
    for p in n.phones:
        keys.add(f"phone:{p}")
    for which in ("github", "linkedin"):
        url = n.links.get(which)
        if url:
            keys.add(f"url:{_norm_url(url)}")
    return keys


def _norm_url(url: str) -> str:
    u = url.strip().lower().rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u


def _fuzzy_name_key(n: NormRecord) -> Optional[str]:
    """Weak key: lowercased last-resort name+company, used only to link records
    that share no strong identifier. Threshold-gated by exact match here."""
    if not n.full_name:
        return None
    company = ""
    if n.experience:
        company = (n.experience[0].get("company") or "").lower()
    return f"name:{n.full_name.lower()}|{company}"


def cluster(records: list[NormRecord]) -> list[list[NormRecord]]:
    """Group records that refer to the same person via shared match keys."""
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    # Strong keys link records directly.
    key_owner: dict[str, int] = {}
    for i, rec in enumerate(records):
        for k in _match_keys(rec):
            if k in key_owner:
                union(i, key_owner[k])
            else:
                key_owner[k] = i

    # Weak name+company key links ONLY records that carry no strong identifier
    # at all. Two records that each have a (different) email/phone are treated as
    # distinct people -- never name-merged -- per the "same name, different
    # contact => two people" rule.
    name_owner: dict[str, int] = {}
    for i, rec in enumerate(records):
        if _match_keys(rec):
            continue  # has a strong key; don't let a name collision merge it
        nk = _fuzzy_name_key(rec)
        if not nk:
            continue
        if nk in name_owner:
            union(i, name_owner[nk])
        else:
            name_owner[nk] = i

    groups: dict[int, list[NormRecord]] = {}
    for i, rec in enumerate(records):
        groups.setdefault(find(i), []).append(rec)
    return list(groups.values())


# --- Scalar conflict resolution ---------------------------------------------
def _pick_scalar(candidates: list[tuple[str, str]]):
    """candidates: list of (value, source). Returns
    (winner_value, winner_source, n_agree, n_conflict) or None if empty.

    Winner = the distinct value whose best-trust source ranks highest; ties go to
    the value with more supporting sources. n_agree = sources backing the winner;
    n_conflict = count of other distinct values (competing claims).
    """
    cands = [(v, s) for v, s in candidates if v not in (None, "")]
    if not cands:
        return None
    groups: dict[str, list[str]] = {}
    display: dict[str, str] = {}
    for v, s in cands:
        key = v.lower() if isinstance(v, str) else str(v)
        groups.setdefault(key, []).append(s)
        display.setdefault(key, v)

    def score(key):
        srcs = groups[key]
        # Deterministic ordering, INDEPENDENT of input order: highest trust, then
        # most agreement, then the more complete (longer) value, then lexical.
        # The last two keys break ties so permuting inputs can't change the winner.
        return (
            max(trust_weight(s) for s in srcs),
            len(srcs),
            len(display[key]),
            display[key],
        )

    best_key = max(groups, key=score)
    best_source = max(groups[best_key], key=trust_weight)
    n_agree = len(groups[best_key])
    n_conflict = len(groups) - 1
    return display[best_key], best_source, n_agree, n_conflict


# --- Build one canonical record from a cluster ------------------------------
def build_canonical(group: list[NormRecord]) -> CanonicalRecord:
    rec = CanonicalRecord()
    prov: list[Provenance] = []
    confs: dict[str, float] = {}

    # ---- list/union fields ----
    rec.emails = _union_simple([e for n in group for e in n.emails])
    if rec.emails:
        srcs = _sources_with(group, lambda n: n.emails)
        prov.append(Provenance("emails", _top_source(srcs), "merged" if len(srcs) > 1 else "normalized"))
        confs["emails"] = field_confidence(_top_source(srcs), len(srcs), 0, rec.emails)

    rec.phones = _union_simple([p for n in group for p in n.phones])
    if rec.phones:
        srcs = _sources_with(group, lambda n: n.phones)
        prov.append(Provenance("phones", _top_source(srcs), "normalized"))
        confs["phones"] = field_confidence(_top_source(srcs), len(srcs), 0, rec.phones)

    # ---- scalar fields with conflict resolution ----
    name = _pick_scalar([(n.full_name, n.source) for n in group])
    if name:
        rec.full_name = name[0]
        prov.append(Provenance("full_name", name[1], "merged" if name[2] > 1 else "direct"))
        confs["full_name"] = field_confidence(name[1], name[2], name[3], name[0])

    headline = _pick_scalar([(n.headline, n.source) for n in group])
    if headline:
        rec.headline = headline[0]
        prov.append(Provenance("headline", headline[1], "direct"))
        confs["headline"] = field_confidence(headline[1], headline[2], headline[3], headline[0])

    yrs = _pick_scalar([(str(n.years_experience), n.source)
                        for n in group if n.years_experience is not None])
    if yrs:
        try:
            rec.years_experience = float(yrs[0])
        except ValueError:
            rec.years_experience = None
        if rec.years_experience is not None:
            prov.append(Provenance("years_experience", yrs[1], "direct"))
            confs["years_experience"] = field_confidence(yrs[1], yrs[2], yrs[3], rec.years_experience)

    # ---- location (pick the most complete, trust-weighted) ----
    loc = _pick_location(group)
    if loc:
        rec.location, loc_src, loc_conf = loc
        prov.append(Provenance("location", loc_src, "normalized"))
        confs["location"] = loc_conf

    # ---- links (union) ----
    merged_links = {"linkedin": None, "github": None, "portfolio": None, "other": []}
    link_srcs: list[str] = []
    for n in group:
        for k, v in n.links.items():
            if not v:
                continue
            if k in ("linkedin", "github", "portfolio"):
                if not merged_links[k]:
                    merged_links[k] = v
                    link_srcs.append(n.source)
            else:
                if v not in merged_links["other"]:
                    merged_links["other"].append(v)
                    link_srcs.append(n.source)
    rec.links = merged_links
    if link_srcs:
        prov.append(Provenance("links", _top_source(link_srcs), "merged" if len(link_srcs) > 1 else "direct"))
        confs["links"] = field_confidence(_top_source(link_srcs), len(link_srcs), 0, "x")

    # ---- skills (union with per-skill confidence + sources) ----
    rec.skills = _merge_skills(group)
    if rec.skills:
        skill_srcs = sorted({s for se in rec.skills for s in se.sources}, key=trust_weight, reverse=True)
        prov.append(Provenance("skills", skill_srcs[0], "merged" if len(skill_srcs) > 1 else "normalized"))
        confs["skills"] = round(sum(se.confidence for se in rec.skills) / len(rec.skills), 3)

    # ---- experience / education (union + dedupe) ----
    rec.experience = _dedupe_dicts(
        [e for n in group for e in n.experience],
        keyer=lambda e: ((e.get("company") or "").lower(), (e.get("title") or "").lower()),
    )
    if rec.experience:
        srcs = _sources_with(group, lambda n: n.experience)
        prov.append(Provenance("experience", _top_source(srcs), "merged" if len(srcs) > 1 else "direct"))
        confs["experience"] = field_confidence(_top_source(srcs), len(srcs), 0, rec.experience)

    rec.education = _dedupe_dicts(
        [e for n in group for e in n.education],
        # Same school + same end year is the same degree, even if one source
        # failed to parse the degree string -> merge and fill in the gaps.
        keyer=lambda e: ((e.get("institution") or "").lower(), (e.get("end_year") or "")),
    )
    if rec.education:
        srcs = _sources_with(group, lambda n: n.education)
        prov.append(Provenance("education", _top_source(srcs), "merged" if len(srcs) > 1 else "direct"))
        confs["education"] = field_confidence(_top_source(srcs), len(srcs), 0, rec.education)

    rec.candidate_id = make_candidate_id(rec.emails, rec.phones, rec.full_name)
    rec.provenance = prov
    rec.field_confidence = confs
    rec.overall_confidence = overall_confidence(confs)
    return rec


# --- helpers ----------------------------------------------------------------
def _union_simple(items: list[str]) -> list[str]:
    out: list[str] = []
    for it in items:
        if it and it not in out:
            out.append(it)
    return out


def _sources_with(group: list[NormRecord], getter) -> list[str]:
    return [n.source for n in group if getter(n)]


def _top_source(sources: list[str]) -> str:
    return max(sources, key=trust_weight) if sources else "unknown"


def _pick_location(group: list[NormRecord]):
    best = None
    best_score = -1.0
    best_src = None
    for n in group:
        if not n.location:
            continue
        filled = sum(1 for v in n.location.values() if v)
        if filled == 0:
            continue
        score = trust_weight(n.source) + 0.1 * filled
        if score > best_score:
            best_score = score
            best = n.location
            best_src = n.source
    if not best:
        return None
    conf = field_confidence(best_src, 1, 0, best)
    return best, best_src, conf


def _merge_skills(group: list[NormRecord]) -> list[SkillEntry]:
    by_name: dict[str, dict] = {}
    for n in group:
        for raw_skill in n.skills:
            canon = canonical_skill(raw_skill)
            if not canon:
                continue
            key = canon.lower()
            entry = by_name.setdefault(key, {"name": canon, "sources": [], "known": is_known(raw_skill)})
            if n.source not in entry["sources"]:
                entry["sources"].append(n.source)
            entry["known"] = entry["known"] or is_known(raw_skill)
    out: list[SkillEntry] = []
    for entry in by_name.values():
        srcs = sorted(entry["sources"], key=trust_weight, reverse=True)
        base = field_confidence(srcs[0], len(srcs), 0, entry["name"])
        # Unknown (non-curated) skills are penalized -- real signal, lower trust.
        conf = round(base * (1.0 if entry["known"] else 0.8), 3)
        out.append(SkillEntry(name=entry["name"], confidence=conf, sources=srcs))
    out.sort(key=lambda s: (-s.confidence, s.name.lower()))
    return out


def _dedupe_dicts(items: list[dict], keyer) -> list[dict]:
    """Dedupe by key, merging in any fields the first occurrence left blank."""
    out: list[dict] = []
    index: dict = {}
    for it in items:
        if not any(it.values()):
            continue
        k = keyer(it)
        if k in index:
            existing = index[k]
            for fk, fv in it.items():
                if not existing.get(fk) and fv:
                    existing[fk] = fv
        else:
            copy = dict(it)
            index[k] = copy
            out.append(copy)
    return out


# --- top-level entry --------------------------------------------------------
def merge_records(raws: list[RawRecord]) -> list[CanonicalRecord]:
    """Normalize, cluster, and build canonical records from raw source records."""
    norms = [normalize_record(r) for r in raws]
    clusters = cluster(norms)
    canon = [build_canonical(g) for g in clusters]
    # Drop identity-less ghost records (e.g. a malformed row whose only value was
    # an invalid email that normalization rejected) -- noise, not a candidate.
    canon = [c for c in canon if c.full_name or c.emails or c.phones]
    # Deterministic output order: by candidate_id.
    canon.sort(key=lambda c: c.candidate_id)
    return canon
