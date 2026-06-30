"""Regenerate the gold Bob/Robert profile snapshot from the sample inputs.

    python -m tests.make_gold
"""
import json
from pathlib import Path

from transformer.pipeline import run

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
GOLD = ROOT / "tests" / "gold" / "bob_profile.json"


def main():
    result = run([
        str(SAMPLES / "recruiter.csv"),
        str(SAMPLES / "ats.json"),
        str(SAMPLES / "resume_bob.txt"),
    ], config={})
    bob = next(p for p in result.profiles if "smith" in (p["full_name"] or "").lower())
    GOLD.parent.mkdir(parents=True, exist_ok=True)
    GOLD.write_text(json.dumps(bob, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote gold -> {GOLD}")


if __name__ == "__main__":
    main()
