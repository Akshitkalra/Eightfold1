"""GitHub adapter (unstructured source).

Uses the public REST API: /users/{login} for profile (name, bio, blog, company,
location) and /users/{login}/repos for inferring skills from repo languages.

Network/HTTP failures (404, rate limit, no connectivity) return [] -- a bad or
missing source must never crash the run. An optional GITHUB_TOKEN env var raises
the rate limit but is not required.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

from ..canonical import RawRecord

_API = "https://api.github.com"
_TIMEOUT = 8


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "candidate-transformer"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch(login: str) -> list[RawRecord]:
    """Fetch a GitHub user as a RawRecord list (0 or 1 records). Never raises."""
    login = (login or "").strip().lstrip("@")
    if not login:
        return []
    try:
        prof = requests.get(f"{_API}/users/{login}", headers=_headers(), timeout=_TIMEOUT)
        if prof.status_code != 200:
            return []
        p = prof.json()
    except (requests.RequestException, ValueError):
        return []

    rec = RawRecord(source="github")
    if p.get("name"):
        rec.full_name = p["name"]
    if p.get("email"):
        rec.emails = [p["email"]]
    if p.get("bio"):
        rec.headline = p["bio"]
    if p.get("location"):
        rec.location = {"city": p["location"], "region": None, "country": p["location"]}

    links: dict = {"github": p.get("html_url")}
    blog = (p.get("blog") or "").strip()
    if blog:
        links["portfolio"] = blog if blog.startswith("http") else f"https://{blog}"
    rec.links = {k: v for k, v in links.items() if v}

    rec.skills = _languages(login)
    return [rec]


def _languages(login: str) -> list[str]:
    """Distinct repo languages -> skill hints. Failures degrade to []."""
    try:
        r = requests.get(
            f"{_API}/users/{login}/repos",
            headers=_headers(),
            params={"per_page": 100, "sort": "pushed"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        repos = r.json()
    except (requests.RequestException, ValueError):
        return []
    langs: list[str] = []
    for repo in repos if isinstance(repos, list) else []:
        lang = repo.get("language")
        if lang and lang not in langs:
            langs.append(lang)
    return langs


def fetch_many(logins: list[str]) -> list[RawRecord]:
    out: list[RawRecord] = []
    for login in logins:
        out.extend(fetch(login))
    return out
