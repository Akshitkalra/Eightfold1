"""ATS JSON adapter (structured source).

Semi-structured: the ATS uses its OWN field names that do NOT match ours, so the
core job here is field remapping. We look up values by a set of likely keys and
tolerate nesting. Malformed JSON yields [] (never raises).

Accepts either a single object or a list of candidate objects.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..canonical import RawRecord


def _first(d: dict, keys: list[str]) -> Optional[Any]:
    """Return the first present, non-empty value among candidate keys (case-insensitive)."""
    lower = {k.lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, "", [], {}):
            return v
    return None


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def parse(text: str) -> list[RawRecord]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    blobs = data if isinstance(data, list) else [data]
    out: list[RawRecord] = []
    for blob in blobs:
        if isinstance(blob, dict):
            rec = _blob_to_record(blob)
            if rec is not None:
                out.append(rec)
    return out


def _blob_to_record(b: dict) -> RawRecord | None:
    rec = RawRecord(source="ats_json")

    # name: either a single field or first/last parts
    name = _first(b, ["full_name", "name", "candidate_name", "fullName"])
    if not name:
        first = _first(b, ["first_name", "firstName", "given_name"])
        last = _first(b, ["last_name", "lastName", "family_name", "surname"])
        name = " ".join(x for x in [first, last] if x) or None
    if name:
        rec.full_name = str(name)

    email = _first(b, ["email", "email_address", "emailAddress", "primaryEmail", "contact_email"])
    if email:
        rec.emails = [str(e) for e in _as_list(email)]

    phone = _first(b, ["phone", "phone_number", "phoneNumber", "mobile", "contact_number"])
    if phone:
        rec.phones = [str(p) for p in _as_list(phone)]

    rec.headline = _maybe_str(_first(b, ["headline", "summary", "objective", "current_title", "title"]))

    yrs = _first(b, ["years_experience", "yearsExperience", "total_experience", "experience_years"])
    if yrs is not None:
        try:
            rec.years_experience = float(yrs)
        except (TypeError, ValueError):
            pass

    # location: nested dict or flat fields
    loc = _first(b, ["location", "address", "geo"])
    city = region = country = None
    if isinstance(loc, dict):
        city = _maybe_str(_first(loc, ["city", "town"]))
        region = _maybe_str(_first(loc, ["region", "state", "province"]))
        country = _maybe_str(_first(loc, ["country", "country_code", "nation"]))
    else:
        city = _maybe_str(_first(b, ["city", "town"]))
        region = _maybe_str(_first(b, ["region", "state", "province"]))
        country = _maybe_str(_first(b, ["country", "country_code", "nation"]))
    if any([city, region, country]):
        rec.location = {"city": city, "region": region, "country": country}

    skills = _first(b, ["skills", "skill_set", "skillset", "competencies", "tags"])
    if skills:
        rec.skills = [str(s) for s in _as_list(skills) if str(s).strip()]

    # links
    links: dict[str, Any] = {}
    li = _maybe_str(_first(b, ["linkedin", "linkedin_url", "linkedinUrl"]))
    gh = _maybe_str(_first(b, ["github", "github_url", "githubUrl"]))
    pf = _maybe_str(_first(b, ["portfolio", "website", "personal_site"]))
    if li:
        links["linkedin"] = li
    if gh:
        links["github"] = gh
    if pf:
        links["portfolio"] = pf
    if links:
        rec.links = links

    # experience
    exp = _first(b, ["experience", "work_history", "employment", "positions"])
    for e in _as_list(exp):
        if isinstance(e, dict):
            rec.experience.append({
                "company": _maybe_str(_first(e, ["company", "employer", "organization", "org"])),
                "title": _maybe_str(_first(e, ["title", "role", "position"])),
                "start": _maybe_str(_first(e, ["start", "start_date", "from", "startDate"])),
                "end": _maybe_str(_first(e, ["end", "end_date", "to", "endDate"])),
                "summary": _maybe_str(_first(e, ["summary", "description", "details"])),
            })

    # education
    edu = _first(b, ["education", "schools", "academics", "qualifications"])
    for e in _as_list(edu):
        if isinstance(e, dict):
            rec.education.append({
                "institution": _maybe_str(_first(e, ["institution", "school", "university", "college"])),
                "degree": _maybe_str(_first(e, ["degree", "qualification"])),
                "field": _maybe_str(_first(e, ["field", "major", "field_of_study", "subject"])),
                "end_year": _maybe_str(_first(e, ["end_year", "graduation_year", "year", "end", "graduated"])),
            })

    # Drop completely empty records.
    if not any([rec.full_name, rec.emails, rec.phones, rec.skills, rec.experience]):
        return None
    return rec


def _maybe_str(v: Any) -> Optional[str]:
    if v in (None, "", [], {}):
        return None
    return str(v)


def parse_file(path: str) -> list[RawRecord]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return parse(f.read())
    except (OSError, UnicodeDecodeError):
        return []
