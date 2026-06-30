# Project Plan — Multi-Source Candidate Data Transformer
**Eightfold Engineering Intern Assignment (Jul–Dec 2026)**
Author: Akshit Kalra · akshit0273.be23@chitkara.edu.in · Stack: **Python 3.11+**

---

## 0. The goal in one sentence
Turn messy, conflicting, multi-source candidate data into **one clean canonical profile** per person — normalized, deduplicated, with **provenance** (where each value came from) and **confidence** (how sure we are) — and let a runtime **config reshape the output** without touching engine code.

Guiding principle from the brief: **wrong-but-confident is worse than honestly-empty.** Never invent values; unknowns become `null`.

---

## 1. Sources we will implement
We exceed the "1 from each group" minimum to make the merge/dedup story strong.

| Group | Source | Format | Adapter responsibility |
|---|---|---|---|
| Structured | Recruiter CSV | `.csv` rows | name, email, phone, current_company, title |
| Structured | ATS JSON blob | `.json` | semi-structured; **field names differ from ours** → map |
| Unstructured | GitHub profile | public REST API | name, bio, repos, languages → skills |
| Unstructured | Resume | `.txt` (+ `.pdf` stretch) | free-text → experience, education, skills |
| Unstructured | LinkedIn profile | URL / saved JSON or text | link (URL) or name, headline, skills, experience, education (export) |
| Unstructured | Recruiter notes | `.txt` free text | name, email, phone, curated skills scanned from prose |

> All six are implemented. LinkedIn is **not** scraped live (auth-walled / ToS);
> a URL contributes the link, a saved export is parsed.

Each adapter is **isolated and optional**. A missing/garbage source logs a warning and yields nothing — it must never crash the run.

---

## 2. Pipeline (the dummy pipeline, our take)

```
            ┌──────────┐
 inputs ──► │  DETECT  │  sniff source type (extension + shape), pick adapter
            └────┬─────┘
                 ▼
            ┌──────────┐
            │ EXTRACT  │  adapter parses raw → list of RawRecord (loose fields + source tag)
            └────┬─────┘
                 ▼
            ┌──────────┐
            │NORMALIZE │  phones→E.164, dates→YYYY-MM, country→ISO-3166-α2, skills→canonical
            └────┬─────┘
                 ▼
            ┌──────────┐
            │  MERGE   │  group records by match key → resolve conflicts per field
            └────┬─────┘
                 ▼
            ┌──────────┐
            │CONFIDENCE│  score each field from source trust × agreement × completeness
            └────┬─────┘
                 ▼
            ┌──────────┐
            │ PROJECT  │  apply runtime config: select/rename/normalize/missing-policy
            └────┬─────┘
                 ▼
            ┌──────────┐
            │ VALIDATE │  check projected output against requested schema → emit JSON
            └──────────┘
```

**Clean separation:** the internal **CanonicalRecord** is always complete and consistent. The **projection layer** is the only thing the config touches. This is the architectural spine the brief explicitly rewards.

---

## 3. Canonical output schema (internal, always full)

```python
candidate_id      : str                      # deterministic hash of strongest identity key
full_name         : str
emails            : list[str]                 # lowercased, deduped
phones            : list[str]                 # E.164
location          : {city, region, country}   # country = ISO-3166 alpha-2
links             : {linkedin, github, portfolio, other[]}
headline          : str | null
years_experience  : number | null
skills            : list[{name, confidence, sources[]}]   # canonical skill names
experience        : list[{company, title, start, end, summary}]  # dates YYYY-MM
education         : list[{institution, degree, field, end_year}]
provenance        : list[{field, source, method}]
overall_confidence: number                    # 0..1
```

---

## 4. Normalization rules (deterministic)
| Field | Rule | Library |
|---|---|---|
| Phones | parse → **E.164** (`+14155550100`) | `phonenumbers` |
| Dates | → `YYYY-MM` (experience), `YYYY` (education end_year) | `dateutil` + custom |
| Country | name/variant → **ISO-3166 alpha-2** | `pycountry` |
| Emails | lowercase, strip, validate shape, dedupe | stdlib `re` |
| Skills | alias map → canonical (`JS`/`Javascript`→`JavaScript`) | local `skills_canonical.json` |
| Names | trim, collapse whitespace, title-case fallback | stdlib |

Anything unparseable → `null` + a provenance note. **Never guess.**

---

## 5. Merge / conflict-resolution policy

**Match keys (in priority order)** to decide two records are the same person:
1. Normalized email (strongest)
2. Normalized phone (E.164)
3. GitHub/LinkedIn URL
4. Fuzzy `full_name` + `current_company` (last resort, threshold-gated)

Records are grouped into clusters; each cluster → one canonical profile.

**Per-field winner selection:**
- **List fields** (emails, phones, skills, links) → **union + dedupe** (keep all, track sources).
- **Scalar fields** (full_name, headline, location, years_experience) → pick by **source trust rank**, breaking ties by **agreement count** (how many sources agree), then **recency/completeness**.

**Source trust ranking (default):**
`ATS JSON ≈ Recruiter CSV  >  Resume  >  GitHub`
(structured/recruiter-curated data outranks scraped free text). Configurable constant, documented.

---

## 6. Confidence model
Per-field confidence `∈ [0,1]`:
```
field_conf = trust_weight(source)        # how reliable is the winning source
           × agreement_factor            # +boost when ≥2 sources agree, −penalty on conflict
           × completeness_factor         # full vs partial value
```
`overall_confidence` = weighted mean of populated field confidences.
Every populated field also gets a **provenance** entry `{field, source, method}` where `method` ∈ {`direct`, `normalized`, `inferred`, `merged`}. Fully traceable → satisfies "deterministic & explainable."

---

## 7. Runtime configurable output (the required twist)
The projection layer reads a JSON config and reshapes output — **same engine, no code changes.**

Config can:
- **Select** a subset of fields.
- **Rename / remap** via `from` path (e.g. `primary_email` from `emails[0]`).
- **Per-field normalization** (e.g. force `E164`, `canonical`).
- **Toggle** provenance / confidence on/off.
- **on_missing policy:** `null` | `omit` | `error`.

```json
{
  "fields": [
    { "path": "full_name",     "type": "string",   "required": true },
    { "path": "primary_email", "from": "emails[0]", "type": "string", "required": true },
    { "path": "phone",         "from": "phones[0]", "type": "string", "normalize": "E164" },
    { "path": "skills",        "from": "skills[].name", "type": "string[]", "normalize": "canonical" }
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```
A small **path resolver** supports `emails[0]` and `skills[].name`. After projection, output is **validated against the requested schema** (types, required, shape) before it's returned.

---

## 8. I/O surface — CLI (lower priority, kept thin)
```bash
python -m transformer \
  --inputs samples/recruiter.csv samples/ats.json samples/resume.txt \
  --github octocat \
  --config configs/custom.json \
  --out out/profiles.json
```
- No `--config` → emit the **default full schema**.
- Reads files + optional GitHub handle, prints/writes JSON. That's it — engine matters, not polish.

---

## 9. Edge cases (pick 3–5 for the design doc)
1. **Same person, conflicting names** ("Bob" vs "Robert Smith") → trust rank + agreement decides; both kept in provenance.
2. **Garbage/empty source** (corrupt JSON, 404 GitHub) → caught per-adapter, warn, continue; never crashes.
3. **Phone in weird formats** (`(415) 555-0100`, `+1-415...`) → all → same E.164; unparseable → `null`.
4. **Skill aliases & noise** (`reactjs`, `React.js`, `REACT`) → one canonical `React`; unknown skills kept verbatim, low confidence.
5. **Two different people, same name** → NOT merged because email/phone differ → distinct profiles.

**Deliberately descoped under time pressure** (state honestly in README):
- LinkedIn scraping (auth-walled) and DOCX parsing → PDF/TXT only.
- ML-based entity resolution → rule-based fuzzy match instead.

---

## 10. Repository structure
```
transformer/
  __init__.py
  detect.py            # source-type sniffing
  adapters/
    csv_recruiter.py
    ats_json.py
    github.py
    resume_text.py
  normalize/
    phones.py  dates.py  country.py  skills.py
  merge.py             # clustering + conflict resolution
  confidence.py
  canonical.py         # CanonicalRecord dataclass
  project.py           # projection + path resolver
  validate.py          # schema validation
  cli.py
data/
  skills_canonical.json
configs/
  default.json  custom.json
samples/               # provided + crafted sample inputs
tests/
  test_normalize.py  test_merge.py  test_project.py  test_e2e.py
  fixtures/  gold/profiles_expected.json
README.md
requirements.txt
PROJECT_PLAN.md        # this file
```

---

## 11. Build sequence (suggested order)
1. **Scaffold + schema** — `CanonicalRecord` dataclass, repo structure, sample inputs.
2. **Adapters** — CSV → ATS JSON → GitHub → Resume (each returns `RawRecord`s).
3. **Normalizers** — phones, dates, country, skills, emails (unit-tested in isolation).
4. **Merge + confidence** — clustering, conflict resolution, scoring + provenance.
5. **Projection + validation** — config engine, path resolver, schema check.
6. **CLI** — wire it all end-to-end; default + one custom config output.
7. **Tests + gold profile** — e2e on samples, one edge-case test.
8. **Deliverables** — README (exact run steps), 1-page design PDF, ~2-min demo video.

---

## 12. Deliverables checklist
- [ ] **Step 1:** one-page design PDF → `AkshitKalra_akshit0273.be23@chitkara.edu.in_Eightfold.pdf` (this doc is the source material).
- [ ] **Step 2:** public GitHub repo — source, README (exact run steps), produced sample output, tests.
- [ ] Default-schema JSON output + ≥1 custom-config JSON output committed.
- [ ] ~2-min demo video: run e2e, show default + custom output, talk through 1 design decision + 1 edge case.
- [ ] README notes assumptions + anything descoped.

---

## 13. Constraints — how we meet them
- **Deterministic & explainable:** pure functions, fixed trust ranks, no randomness; every field has provenance.
- **Robust:** per-adapter try/except; missing/garbage → warn + skip, unknowns → `null`, never invented.
- **Scale:** streaming/iterator-based adapters, O(n) clustering by hashed match keys → fine for thousands of candidates.
