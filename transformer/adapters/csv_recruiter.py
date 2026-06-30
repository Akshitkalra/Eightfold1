"""Recruiter CSV adapter (structured source).

Expected-ish columns (case/space tolerant): name, email, phone,
current_company, title. Unknown columns are ignored; missing columns are fine.
Normalization is deferred to the merge stage so every adapter stays thin and
each value keeps its source tag.
"""
from __future__ import annotations

import csv
import io
from typing import Iterable

from ..canonical import RawRecord

# Map of canonical field -> accepted header variants (lowercased, stripped).
_HEADER_MAP = {
    "full_name": {"name", "full name", "full_name", "candidate", "candidate name"},
    "email": {"email", "e-mail", "email address", "emails"},
    "phone": {"phone", "phone number", "mobile", "contact", "phones"},
    "company": {"current_company", "current company", "company", "employer"},
    "title": {"title", "current title", "role", "position", "job title"},
    "location": {"location", "city", "address"},
}


def _resolve_headers(fieldnames: list[str]) -> dict[str, str]:
    """Return {canonical_field: actual_header} for headers we recognize."""
    resolved: dict[str, str] = {}
    for actual in fieldnames or []:
        key = (actual or "").strip().lower()
        for canon, variants in _HEADER_MAP.items():
            if key in variants and canon not in resolved:
                resolved[canon] = actual
    return resolved


def parse(text: str) -> list[RawRecord]:
    """Parse CSV text into RawRecords. Malformed CSV yields [] (never raises)."""
    try:
        # Strip a leading UTF-8 BOM (Excel exports) so the first header matches.
        if text and text[0] == "﻿":
            text = text[1:]
        reader = csv.DictReader(io.StringIO(text))
        headers = _resolve_headers(reader.fieldnames or [])
        records: list[RawRecord] = []
        for row in reader:
            rec = _row_to_record(row, headers)
            if rec is not None:
                records.append(rec)
        return records
    except (csv.Error, UnicodeDecodeError):
        return []


def _row_to_record(row: dict, headers: dict[str, str]) -> RawRecord | None:
    def get(field: str) -> str:
        col = headers.get(field)
        return (row.get(col) or "").strip() if col else ""

    name = get("full_name")
    email = get("email")
    phone = get("phone")
    company = get("company")
    title = get("title")
    location_raw = get("location")

    # Drop fully empty rows.
    if not any([name, email, phone, company, title]):
        return None

    rec = RawRecord(source="recruiter_csv")
    if name:
        rec.full_name = name
    if email:
        rec.emails = [email]
    if phone:
        rec.phones = [phone]
    if title:
        rec.headline = title
    if title or company:
        rec.experience = [{
            "company": company or None,
            "title": title or None,
            "start": None, "end": None, "summary": None,
        }]
    if location_raw:
        # Recruiter CSV usually gives a single string; treat as country hint only
        # if it's short, else as city. Keep it simple and explainable.
        rec.location = {"city": location_raw, "region": None, "country": location_raw}
    return rec


def parse_file(path: str) -> list[RawRecord]:
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return parse(f.read())
    except (OSError, UnicodeDecodeError):
        return []
