"""Email normalization: lowercase, trim, shape-validate, dedupe.

Invalid-shaped strings are dropped (not invented/repaired).
"""
from __future__ import annotations

import re
from typing import Optional

# Pragmatic RFC-5322-ish check: good enough to reject garbage without
# rejecting real-world addresses.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def normalize_email(raw: Optional[str]) -> Optional[str]:
    """Return a lowercased, validated email, or None if it doesn't look like one."""
    if not raw or not str(raw).strip():
        return None
    e = str(raw).strip().lower()
    return e if _EMAIL_RE.match(e) else None


def normalize_emails(raws: list[str]) -> list[str]:
    """Normalize a list of emails, dropping invalid ones, deduped, order-stable."""
    out: list[str] = []
    for r in raws:
        e = normalize_email(r)
        if e and e not in out:
            out.append(e)
    return out


def extract_emails(text: str) -> list[str]:
    """Pull all email-shaped substrings out of free text (resume/notes)."""
    found = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text or "")
    return normalize_emails(found)
