"""End-to-end test on the sample inputs + a gold-profile comparison.

Runs the offline file sources (no network) and asserts the merged Bob/Robert
profile matches a committed gold snapshot. Regenerate the gold with:
    python -m tests.make_gold
"""
import json
from pathlib import Path

from transformer.pipeline import run

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
GOLD = ROOT / "tests" / "gold" / "bob_profile.json"


def _run_offline():
    return run([
        str(SAMPLES / "recruiter.csv"),
        str(SAMPLES / "ats.json"),
        str(SAMPLES / "resume_bob.txt"),
    ], config={})


def _bob(profiles):
    return next(p for p in profiles if "smith" in (p["full_name"] or "").lower())


def test_pipeline_runs_and_merges_smith():
    result = _run_offline()
    # Bob/Robert from 3 sources + Jane + Mei + Priya = 4 distinct people.
    names = sorted(p["full_name"] for p in result.profiles)
    assert names == ["Jane Doe", "Mei Chen", "Priya Nair", "Robert Smith"]


def test_garbage_sources_do_not_crash():
    result = run([str(SAMPLES / "nope.csv")], github_logins=[], config={})
    assert result.profiles == []
    assert any("not found" in w for w in result.warnings)


def test_bob_matches_gold_profile():
    bob = _bob(_run_offline().profiles)
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    # candidate_id is derived deterministically; compare the whole record.
    assert bob == gold


def test_deterministic_across_runs():
    a = _bob(_run_offline().profiles)
    b = _bob(_run_offline().profiles)
    assert a == b
