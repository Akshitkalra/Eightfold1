"""Source detection + dispatch.

Sniffs each input path by extension first, then by content shape as a fallback,
and routes it to the right adapter. A source that fails to load contributes
nothing (logged) rather than crashing the run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .adapters import ats_json, csv_recruiter, resume_text
from .canonical import RawRecord


def _sniff_text(path: Path) -> str:
    """Decide adapter for an ambiguous text file by content shape."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000].lstrip()
    except OSError:
        return "resume"
    if head.startswith("{") or head.startswith("["):
        return "ats_json"
    # CSV heuristic: first line has commas and looks like headers
    first_line = head.splitlines()[0] if head.splitlines() else ""
    if "," in first_line and "@" not in first_line:
        return "csv"
    return "resume"


def adapter_for(path: str) -> tuple[str, Callable[[str], list[RawRecord]]]:
    """Return (source_label, parse_file_fn) for a given input path."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return "recruiter_csv", csv_recruiter.parse_file
    if ext == ".json":
        return "ats_json", ats_json.parse_file
    if ext in (".txt", ".pdf", ".docx", ".md"):
        # .txt could be a CSV-ish export or a resume; sniff content.
        if ext == ".txt" and _sniff_text(p) == "csv":
            return "recruiter_csv", csv_recruiter.parse_file
        if ext == ".txt" and _sniff_text(p) == "ats_json":
            return "ats_json", ats_json.parse_file
        return "resume", resume_text.parse_file
    # Unknown extension: sniff content.
    kind = _sniff_text(p)
    return {
        "csv": ("recruiter_csv", csv_recruiter.parse_file),
        "ats_json": ("ats_json", ats_json.parse_file),
        "resume": ("resume", resume_text.parse_file),
    }[kind]


def load_path(path: str, warnings: list[str] | None = None) -> list[RawRecord]:
    """Detect + parse one input path. Records a warning on empty/garbage source."""
    label, fn = adapter_for(path)
    if not Path(path).exists():
        if warnings is not None:
            warnings.append(f"input not found, skipped: {path}")
        return []
    records = fn(path)
    if not records and warnings is not None:
        warnings.append(f"no records extracted from {label} source: {path}")
    return records
