"""Thin CLI surface.

    python -m transformer --inputs a.csv b.json resume.txt \
        --github octocat --config configs/custom.json --out out/profiles.json

No --config  -> default full canonical schema.
No --out     -> pretty-print JSON to stdout.
Validation errors are reported to stderr but do not change the exit code unless
--strict is passed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import run


def _load_config(path: str | None) -> dict:
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: could not load config {path}: {e}", file=sys.stderr)
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="transformer",
        description="Multi-source candidate data transformer.",
    )
    ap.add_argument("--inputs", nargs="*", default=[],
                    help="input files (CSV / ATS JSON / resume .txt|.pdf)")
    ap.add_argument("--github", nargs="*", default=[],
                    help="GitHub login(s) to fetch as an unstructured source")
    ap.add_argument("--linkedin", nargs="*", default=[],
                    help="LinkedIn profile URL(s), saved profile file(s), or inline JSON")
    ap.add_argument("--notes", nargs="*", default=[],
                    help="recruiter notes .txt file(s) (free text)")
    ap.add_argument("--config", default=None,
                    help="projection config JSON (omit for default schema)")
    ap.add_argument("--out", default=None,
                    help="write JSON here (omit to print to stdout)")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any output fails schema validation")
    args = ap.parse_args(argv)

    config = _load_config(args.config)
    result = run(args.inputs, github_logins=args.github,
                 linkedin_inputs=args.linkedin, notes_paths=args.notes,
                 config=config)

    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    if result.validation:
        for idx, errs in result.validation.items():
            for e in errs:
                print(f"validation[{idx}]: {e}", file=sys.stderr)

    payload = json.dumps(result.profiles, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"wrote {len(result.profiles)} profile(s) -> {args.out}", file=sys.stderr)
    else:
        print(payload)

    if args.strict and result.validation:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
