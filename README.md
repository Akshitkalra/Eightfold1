# Multi-Source Candidate Data Transformer

Turns messy, conflicting candidate data from many sources into **one clean
canonical profile per person** — normalized, deduplicated, with **provenance**
(where each value came from) and **confidence** (how sure we are). A runtime
**config** reshapes the output with no code changes.

> Guiding rule: *wrong-but-confident is worse than honestly-empty.* Unknown
> values become `null` — never invented.

Author: **Akshit Kalra** · akshit0273.be23@chitkara.edu.in

---

## What it does (pipeline)

```
DETECT → EXTRACT → NORMALIZE → MERGE → CONFIDENCE → PROJECT → VALIDATE
```

The internal **CanonicalRecord** is always complete and consistent. The
**projection layer** (`project.py`) is the *only* thing the runtime config
touches — so config changes never require engine changes.

| Group | Source | Adapter |
|---|---|---|
| Structured | Recruiter CSV | [`csv_recruiter.py`](transformer/adapters/csv_recruiter.py) |
| Structured | ATS JSON (own field names) | [`ats_json.py`](transformer/adapters/ats_json.py) |
| Unstructured | GitHub profile (live REST API) | [`github.py`](transformer/adapters/github.py) |
| Unstructured | Resume `.txt` (`.pdf` optional) | [`resume_text.py`](transformer/adapters/resume_text.py) |
| Unstructured | LinkedIn profile (URL / saved export) | [`linkedin.py`](transformer/adapters/linkedin.py) |
| Unstructured | Recruiter notes (`.txt` free text) | [`recruiter_notes.py`](transformer/adapters/recruiter_notes.py) |

> **LinkedIn note:** live scraping is auth-walled and against LinkedIn's ToS, so
> we never fetch it over the network. A profile **URL** contributes the
> canonical link only (still useful for merge/dedup); a **saved/exported profile**
> (JSON or text) is parsed for name, headline, skills, experience, education.

---

## Quickstart (30 seconds)

```bash
pip install -r requirements.txt
python -m transformer --inputs samples/recruiter.csv samples/ats.json samples/resume_bob.txt --out out/default.json
python -m pytest -q
```
First command installs deps; second produces a canonical profile JSON from the
sample inputs; third runs all 310 tests. Requires **Python 3.11+**.

---

## Setup (with a virtual environment, recommended)

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Windows (CMD):         .venv\Scripts\activate.bat
# macOS / Linux:         source .venv/bin/activate
pip install -r requirements.txt
```
Requires Python 3.11+. No API keys needed (GitHub source works unauthenticated;
set `GITHUB_TOKEN` only to raise the rate limit).

---

## Run

> Every command below is a **single line** so it copy-pastes cleanly into any
> shell — Windows PowerShell / CMD **and** macOS / Linux / Git Bash.

**Default canonical schema** (offline file sources):
```bash
python -m transformer --inputs samples/recruiter.csv samples/ats.json samples/resume_bob.txt --out out/default.json
```

**Custom config** (rename/remap, normalize, drop provenance):
```bash
python -m transformer --inputs samples/recruiter.csv samples/ats.json samples/resume_bob.txt --config configs/custom.json --out out/custom.json
```

**Add the live GitHub source** (optional: set `GITHUB_TOKEN` to raise the API rate limit):
```bash
python -m transformer --github octocat --out out/github.json
```

**All six sources at once** (one person merged across five — see [`out/all_sources.json`](out/all_sources.json)):
```bash
python -m transformer --inputs samples/recruiter.csv samples/ats.json samples/resume_bob.txt --linkedin samples/linkedin_bob.json --notes samples/notes_bob.txt --out out/all_sources.json
```
`--linkedin` accepts a profile URL, a saved profile file, or inline JSON.
`--notes` takes recruiter notes `.txt` file(s).

**Print to stdout** (omit `--out`); **fail on schema violations** (add `--strict`).

Produced sample outputs are committed in [`out/`](out/).

### Minimal web UI (optional)

A small Flask UI ([`webui/`](webui/)) wraps the same `pipeline.run` — no engine
logic lives in it. Pick sources, add a GitHub handle, choose a config, and view
the merged profiles as cards (confidence bars, skill chips, provenance tables)
plus the raw JSON.

```bash
pip install flask
python -m webui.app          # open http://127.0.0.1:5000
```

---

## The configurable-output twist

The config reshapes output — same engine, no code changes. See
[`configs/custom.json`](configs/custom.json):

```json
{
  "fields": [
    { "path": "full_name",     "type": "string",   "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone",         "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills",        "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "include_provenance": false,
  "on_missing": "null"
}
```

The config can:
- **Select** a subset of fields.
- **Rename / remap** via a `from` path — supports `emails[0]`, `location.country`, `skills[].name`.
- **Per-field normalization**: `E164`, `canonical`, `lower`, `upper`.
- **Toggle** `include_provenance` / `include_confidence`.
- **`on_missing`**: `null` | `omit` | `error`.

Output is **validated** against the requested schema (types + required) before return.

---

## Design decisions

**Merge / match keys** (in priority): normalized email → E.164 phone →
github/linkedin URL → (last resort) exact name+company *only for records with no
strong identifier*. Records are clustered with union-find; each cluster → one
profile.

**Conflict resolution.** List fields (emails, phones, skills, links) are
**unioned + deduped**. Scalar fields (name, headline, location, years) pick a
**winner by source trust × agreement count × completeness**. Trust ranking:
`ATS > Recruiter CSV > LinkedIn > Resume > Recruiter notes > GitHub` (see
`SOURCE_TRUST` in [`canonical.py`](transformer/canonical.py)). Ties are broken
deterministically (completeness, then lexical) so input order never changes the
winner.

**Confidence.** `trust_weight(source) × agreement_factor × completeness_factor`,
clamped to `[0,1]`; `overall_confidence` is the weighted mean over populated
fields. Every populated field also gets a provenance entry
`{field, source, method}` where method ∈ `direct | normalized | inferred | merged`.

**Normalization.** phones → E.164 · dates → `YYYY-MM` (experience) / `YYYY`
(education) · country → ISO-3166 alpha-2 · skills → canonical names · emails →
lowercased + validated.

---

## Edge cases handled

1. **Same person, conflicting names** — "Bob Smith" (CSV) vs "Robert Smith"
   (ATS) → merged via shared email; higher-trust "Robert Smith" wins, both kept
   in provenance.
2. **Same name, different people** — same name but different emails → **not
   merged** (two profiles). Covered by a test.
3. **Garbage / missing source** — corrupt JSON, missing file, 404 GitHub →
   warned and skipped; the run never crashes.
4. **Phone format chaos** — `(415) 555-0100` and `+1-415-555-0100` collapse to
   one `+14155550100`; unparseable → `null`.
5. **Skill aliases** — `reactjs`, `React.js`, `REACT` → one canonical `React`;
   unknown skills kept verbatim at lower confidence.

**Deliberately descoped (time):** LinkedIn scraping (auth-walled), DOCX parsing
(PDF/TXT only), ML-based entity resolution (rule-based fuzzy match instead). A
bare non-US phone with no country code (e.g. a 10-digit Indian number) is
dropped rather than guessed — honest-empty over wrong-but-confident.

---

## Tests

```bash
python -m pytest -q          # 310 tests: normalizers, adapters, merge, projection, edge cases, e2e + gold
python -m tests.make_gold    # regenerate the gold snapshot after intended changes
```

- [`test_normalize.py`](tests/test_normalize.py) — deterministic normalizers.
- [`test_merge.py`](tests/test_merge.py) — clustering, conflict resolution, the
  same-name-different-people edge case, determinism.
- [`test_project.py`](tests/test_project.py) — path resolver, rename/normalize,
  `on_missing` policies, validation.
- [`test_e2e.py`](tests/test_e2e.py) — full pipeline on samples + gold-profile
  comparison.

---

## Project layout

```
transformer/
  detect.py            source sniffing + dispatch
  canonical.py         RawRecord / CanonicalRecord / trust ranks / id
  adapters/            csv_recruiter, ats_json, github, resume_text, linkedin, recruiter_notes
  normalize/           phones, dates, country, skills, emails
  merge.py             normalize → cluster → resolve → score
  confidence.py        per-field + overall confidence
  project.py           projection layer + path resolver
  validate.py          output schema validation
  pipeline.py          end-to-end wiring
  cli.py               thin CLI surface
webui/                 minimal Flask UI (app.py, templates/, static/)
data/skills_canonical.json
configs/   default.json  custom.json
samples/   recruiter.csv  ats.json  resume_bob.txt
out/       default.json   custom.json        (produced outputs)
tests/     + gold/bob_profile.json
```

## Constraints met
- **Deterministic & explainable** — pure functions, fixed trust ranks, no
  randomness; output ordered by `candidate_id`; every field traceable via
  provenance.
- **Robust** — per-adapter try/except; bad/missing source → warn + skip;
  unknowns → `null`, never invented.
- **Scale** — iterator-based adapters and O(n) union-find clustering by hashed
  keys; fine for thousands of candidates.
