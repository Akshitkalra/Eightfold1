"""Minimal Flask UI for the candidate transformer.

Thin layer over transformer.pipeline.run -- NO engine logic lives here. It lets
you pick the sample inputs (or upload your own), add a GitHub handle, choose a
projection config, and view the resulting canonical profiles rendered as cards
plus the raw JSON.

Run:
    python -m webui.app           # then open http://127.0.0.1:5000
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from flask import Flask, render_template, request

from transformer.pipeline import run

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
CONFIGS = ROOT / "configs"

# Sample files offered as checkboxes (label -> path).
SAMPLE_FILES = {
    "Recruiter CSV (structured)": SAMPLES / "recruiter.csv",
    "ATS JSON (structured)": SAMPLES / "ats.json",
    "Resume .txt (unstructured)": SAMPLES / "resume_bob.txt",
}

app = Flask(__name__)


def _load_config(choice: str, pasted: str) -> dict:
    if choice == "custom":
        try:
            return json.loads((CONFIGS / "custom.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    if choice == "paste" and pasted.strip():
        try:
            return json.loads(pasted)
        except json.JSONDecodeError as e:
            raise ValueError(f"Pasted config is not valid JSON: {e}") from e
    return {}  # default full schema


@app.route("/", methods=["GET", "POST"])
def index():
    ctx = {
        "sample_files": SAMPLE_FILES,
        "selected": list(SAMPLE_FILES.keys()),  # all checked by default
        "github": "",
        "config_choice": "default",
        "pasted_config": "",
        "profiles": None,
        "warnings": [],
        "validation": {},
        "raw_json": "",
        "error": None,
        "count": 0,
    }

    if request.method == "POST":
        selected = request.form.getlist("samples")
        github = (request.form.get("github") or "").strip()
        config_choice = request.form.get("config_choice", "default")
        pasted = request.form.get("pasted_config", "")
        ctx.update(selected=selected, github=github,
                   config_choice=config_choice, pasted_config=pasted)

        input_paths = [str(SAMPLE_FILES[label]) for label in selected if label in SAMPLE_FILES]

        # Handle uploaded files (saved to a temp dir, original extension preserved).
        tmpdir = tempfile.mkdtemp(prefix="transformer_ui_")
        for f in request.files.getlist("uploads"):
            if f and f.filename:
                dest = Path(tmpdir) / Path(f.filename).name
                f.save(str(dest))
                input_paths.append(str(dest))

        try:
            config = _load_config(config_choice, pasted)
        except ValueError as e:
            ctx["error"] = str(e)
            return render_template("index.html", **ctx)

        logins = [github] if github else []
        result = run(input_paths, github_logins=logins, config=config)
        ctx.update(
            profiles=result.profiles,
            warnings=result.warnings,
            validation=result.validation,
            raw_json=json.dumps(result.profiles, indent=2, ensure_ascii=False),
            count=len(result.profiles),
        )

    return render_template("index.html", **ctx)


@app.template_filter("pct")
def pct(value):
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return "-"


if __name__ == "__main__":
    app.run(debug=True, port=5000)
