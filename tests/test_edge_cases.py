"""Adversarial edge cases: unicode, ordering/determinism, malformed inputs,
deep config paths, trust ties, scale, and other corner conditions."""
import itertools
import json

import pytest

from transformer.adapters import csv_recruiter, ats_json, resume_text
from transformer.canonical import RawRecord
from transformer.merge import merge_records
from transformer.project import project, resolve_path
from transformer.pipeline import run


def R(**kw):
    return RawRecord(source=kw.pop("source", "recruiter_csv"), **kw)


# ============================ unicode / i18n ===============================
def test_unicode_name_preserved():
    out = merge_records([R(full_name="José García", emails=["jose@x.com"])])
    assert out[0].full_name == "José García"


def test_cjk_name_preserved():
    out = merge_records([R(full_name="李明", emails=["li@x.com"])])
    assert out[0].full_name == "李明"


def test_unicode_survives_json_serialization():
    out = merge_records([R(full_name="Zoë Müller", emails=["z@x.com"])])
    s = json.dumps(out[0].to_dict(), ensure_ascii=False)
    assert "Zoë Müller" in s


def test_emoji_in_headline_does_not_crash():
    out = merge_records([R(full_name="Bob", emails=["b@x.com"], headline="ships fast 🚀")])
    assert "🚀" in out[0].headline


# ============================ ordering / determinism =======================
def test_output_identical_under_input_permutation():
    recs = [
        R(source="recruiter_csv", full_name="Bob", emails=["x@y.com"]),
        R(source="ats_json", full_name="Robert Smith", emails=["x@y.com"], skills=["Python"]),
        R(source="resume", full_name="Bobby", emails=["x@y.com"], skills=["python", "aws"]),
    ]
    baseline = json.dumps([c.to_dict() for c in merge_records(recs)], sort_keys=True)
    for perm in itertools.permutations(recs):
        got = json.dumps([c.to_dict() for c in merge_records(list(perm))], sort_keys=True)
        assert got == baseline


def test_scalar_tie_break_is_deterministic_under_permutation():
    # Two equal-trust sources disagree -> winner must not depend on input order.
    a = R(source="recruiter_csv", full_name="Alice", emails=["x@y.com"])
    b = R(source="recruiter_csv", full_name="Alicia", emails=["x@y.com"])
    n1 = merge_records([a, b])[0].full_name
    n2 = merge_records([b, a])[0].full_name
    assert n1 == n2


def test_skill_order_deterministic():
    out1 = merge_records([R(full_name="B", emails=["x@y.com"], skills=["aws", "python", "react"])])
    out2 = merge_records([R(full_name="B", emails=["x@y.com"], skills=["react", "aws", "python"])])
    assert [s.name for s in out1[0].skills] == [s.name for s in out2[0].skills]


# ============================ malformed structured =========================
def test_csv_quoted_field_with_comma():
    recs = csv_recruiter.parse('name,title\n"Smith, Bob","Engineer, Senior"\n')
    assert recs[0].full_name == "Smith, Bob"
    assert recs[0].headline == "Engineer, Senior"


def test_csv_quoted_newline_inside_field():
    recs = csv_recruiter.parse('name,title\nBob,"line1\nline2"\n')
    assert recs[0].full_name == "Bob"


def test_csv_bom_header():
    recs = csv_recruiter.parse("﻿name,email\nBob,bob@x.com\n")
    assert recs and recs[0].full_name == "Bob"


def test_csv_extra_columns_in_row():
    # ragged row: more values than headers -> must not crash
    recs = csv_recruiter.parse("name,email\nBob,bob@x.com,extra,more\n")
    assert recs and recs[0].full_name == "Bob"


def test_csv_only_headers_no_rows():
    assert csv_recruiter.parse("name,email,phone\n") == []


def test_ats_deeply_nested_and_nulls():
    blob = json.dumps({"name": "Bob", "email": None, "skills": None,
                       "address": {"city": None, "country": "USA"}})
    recs = ats_json.parse(blob)
    assert recs and recs[0].location["country"] == "USA"


def test_ats_top_level_array_with_garbage_mixed():
    blob = '[{"name":"Bob","email":"b@x.com"}, "junk-string", 42, null, {"nope":1}]'
    recs = ats_json.parse(blob)
    assert len(recs) == 1 and recs[0].full_name == "Bob"


def test_ats_unicode_escapes():
    recs = ats_json.parse('{"name":"Jos\\u00e9","email":"j@x.com"}')
    assert recs[0].full_name == "José"


# ============================ phones / contact corner ======================
def test_phone_with_extension():
    out = merge_records([R(full_name="B", phones=["+1 415-555-0100 x123"])])
    # extension may be dropped or kept; base number must still normalize
    assert out[0].phones and out[0].phones[0].startswith("+1415555")


def test_duplicate_emails_within_one_record_deduped():
    out = merge_records([R(full_name="B", emails=["a@x.com", "A@X.com", "a@x.com"])])
    assert out[0].emails == ["a@x.com"]


def test_email_case_difference_merges_people():
    out = merge_records([
        R(source="recruiter_csv", full_name="Bob", emails=["Bob@X.com"]),
        R(source="ats_json", full_name="Robert", emails=["bob@x.com"]),
    ])
    assert len(out) == 1  # case-folded email is the same identity


# ============================ skills corner ================================
@pytest.mark.parametrize("raw", ["C++", "C#", ".NET", "Node.js", "scikit-learn"])
def test_punctuation_heavy_skills_survive(raw):
    out = merge_records([R(full_name="B", emails=["x@y.com"], skills=[raw])])
    assert out[0].skills  # not dropped


# ============================ deep config paths ============================
def test_resolve_nested_list_index_then_field():
    data = {"experience": [{"company": "Acme", "title": "Eng"}]}
    assert resolve_path(data, "experience[0].company") == "Acme"
    assert resolve_path(data, "experience[0].title") == "Eng"


def test_project_deep_path_from_experience():
    raw = R(source="ats_json", full_name="Bob", emails=["b@x.com"],
            experience=[{"company": "Acme", "title": "Eng", "start": "2020", "end": "2022"}])
    rec = merge_records([raw])[0]
    out = project(rec, {"fields": [{"path": "first_company", "from": "experience[0].company"}]})
    assert out["first_company"] == "Acme"


def test_project_whole_list_field():
    raw = R(source="ats_json", full_name="Bob", emails=["a@x.com", "b@y.com"])
    rec = merge_records([raw])[0]
    out = project(rec, {"fields": [{"path": "all_emails", "from": "emails"}]})
    assert out["all_emails"] == rec.emails


# ============================ config robustness ============================
def test_config_missing_on_missing_defaults_to_null():
    raw = R(source="ats_json", full_name="Bob", emails=["b@x.com"])
    rec = merge_records([raw])[0]
    out = project(rec, {"fields": [{"path": "x", "from": "nope"}]})  # no on_missing key
    assert out["x"] is None


def test_empty_fields_list_is_default_schema():
    raw = R(source="ats_json", full_name="Bob", emails=["b@x.com"])
    rec = merge_records([raw])[0]
    out = project(rec, {"fields": []})
    assert "candidate_id" in out


def test_years_experience_as_string_number():
    recs = ats_json.parse('{"name":"Bob","email":"b@x.com","years_experience":"7"}')
    out = merge_records(recs)
    assert out[0].years_experience == 7.0


# ============================ scale / robustness ===========================
def test_scale_thousand_candidates():
    raws = [R(source="recruiter_csv", full_name=f"Person {i}",
              emails=[f"person{i}@x.com"]) for i in range(1000)]
    out = merge_records(raws)
    assert len(out) == 1000
    # deterministic ordering holds at scale
    ids = [c.candidate_id for c in out]
    assert ids == sorted(ids)


def test_pipeline_all_empty_inputs():
    result = run([], github_logins=[], config={})
    assert result.profiles == []


def test_pipeline_mixed_good_and_garbage(tmp_path):
    good = tmp_path / "g.csv"
    good.write_text("name,email\nBob,bob@x.com\n", encoding="utf-8")
    bad = tmp_path / "b.json"
    bad.write_text("{not json", encoding="utf-8")
    result = run([str(good), str(bad), str(tmp_path / "missing.txt")], config={})
    assert len(result.profiles) == 1
    assert len(result.warnings) >= 1


def test_whitespace_only_fields_become_null():
    out = merge_records([R(full_name="   ", emails=["b@x.com"], headline="   ")])
    assert out[0].full_name == "" or out[0].full_name is None or out[0].full_name == ""
    assert out[0].headline is None
