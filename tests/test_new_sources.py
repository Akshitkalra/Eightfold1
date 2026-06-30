"""Tests for the LinkedIn and recruiter-notes adapters + their 5-source merge."""
import json
from pathlib import Path

import pytest

from transformer.adapters import linkedin, recruiter_notes
from transformer.canonical import trust_weight
from transformer.pipeline import run

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


# ----------------------------- recruiter notes -----------------------------
def test_notes_extracts_name_email_phone_skills():
    rec = recruiter_notes.parse(
        "Spoke with Robert Smith. Strong in Python and AWS. "
        "Reach bob@x.com / (415) 555-0100.")[0]
    assert rec.full_name == "Robert Smith"
    assert rec.emails == ["bob@x.com"]
    assert any("415" in p for p in rec.phones)
    assert set(rec.skills) == {"Python", "AWS"}


def test_notes_name_label_form():
    rec = recruiter_notes.parse("Name: Mary Jane Watson — react, node")[0]
    assert rec.full_name == "Mary Jane Watson"
    assert set(rec.skills) == {"React", "Node.js"}


def test_notes_name_stops_at_sentence_boundary():
    rec = recruiter_notes.parse("Spoke with Bob Smith. Great fit. x@y.com")[0]
    assert rec.full_name == "Bob Smith"


def test_notes_only_skills_scanned_not_invented():
    rec = recruiter_notes.parse("Candidate knows widgets and frobnication. a@b.com")[0]
    assert rec.skills == []  # no curated skill words present


def test_notes_empty_returns_empty():
    assert recruiter_notes.parse("") == []
    assert recruiter_notes.parse("   \n ") == []


def test_notes_source_is_low_trust():
    assert trust_weight("recruiter_notes") < trust_weight("resume")


def test_notes_missing_file():
    assert recruiter_notes.parse_file("nope/notes.txt") == []


# ----------------------------- linkedin ------------------------------------
def test_linkedin_url_only_contributes_link_no_invention():
    recs = linkedin.parse_input("https://www.linkedin.com/in/janedoe")
    assert len(recs) == 1
    assert recs[0].links["linkedin"] == "https://linkedin.com/in/janedoe"
    assert recs[0].full_name is None  # never invented from a URL


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/in/bob",
    "http://linkedin.com/in/bob",
    "linkedin.com/in/bob",
    "https://in.linkedin.com/in/bob",
])
def test_linkedin_url_variants_normalize(url):
    recs = linkedin.parse_input(url)
    assert recs[0].links["linkedin"] == "https://linkedin.com/in/bob"


def test_linkedin_json_profile():
    blob = json.dumps({
        "name": "Robert Smith", "headline": "Staff Eng",
        "url": "https://linkedin.com/in/bobsmith",
        "location": {"city": "SF", "country": "United States"},
        "skills": ["Python", "Kubernetes"],
        "experience": [{"company": "Acme", "title": "Staff Eng", "start": "2021-03", "end": "present"}],
        "education": [{"school": "Stanford", "degree": "B.S.", "field": "CS", "end_year": "2018"}],
    })
    rec = linkedin.parse_input(blob)[0]
    assert rec.source == "linkedin"
    assert rec.full_name == "Robert Smith"
    assert rec.skills == ["Python", "Kubernetes"]
    assert rec.experience[0]["company"] == "Acme"
    assert rec.education[0]["institution"] == "Stanford"
    assert rec.links["linkedin"] == "https://linkedin.com/in/bobsmith"


def test_linkedin_garbage_returns_empty():
    assert linkedin.parse_input("not a url or json or file") == []
    assert linkedin.parse_input("") == []


def test_linkedin_text_profile_file_tagged_as_linkedin(tmp_path):
    f = tmp_path / "profile.txt"
    f.write_text("Robert Smith\n\nSkills\nPython, AWS\n", encoding="utf-8")
    recs = linkedin.parse_file(str(f))
    assert recs and recs[0].source == "linkedin"
    assert "Python" in recs[0].skills


# ----------------------------- 5-source merge ------------------------------
def test_five_source_merge_of_bob():
    result = run(
        [str(SAMPLES / "recruiter.csv"), str(SAMPLES / "ats.json"), str(SAMPLES / "resume_bob.txt")],
        linkedin_inputs=[str(SAMPLES / "linkedin_bob.json")],
        notes_paths=[str(SAMPLES / "notes_bob.txt")],
        config={},
    )
    bob = next(p for p in result.profiles if "smith" in (p["full_name"] or "").lower())
    sources = {s for sk in bob["skills"] for s in sk["sources"]}
    # all four skill-bearing sources contributed
    assert {"ats_json", "linkedin", "resume", "recruiter_notes"} <= sources
    # a skill agreed on by 4 sources should be maximally confident
    top = {s["name"]: s for s in bob["skills"]}
    assert top["Python"]["confidence"] == 1.0
    # still one merged person, not five
    assert sum(1 for p in result.profiles if "smith" in (p["full_name"] or "").lower()) == 1
