"""Deeper coverage for the path resolver, projection, and validation."""
import pytest

from transformer.canonical import RawRecord
from transformer.merge import merge_records
from transformer.project import project, resolve_path, ProjectionError, _MISSING
from transformer.validate import validate_output


DATA = {
    "emails": ["a@x.com", "b@y.com"],
    "phones": ["+14155550100"],
    "skills": [{"name": "Python", "confidence": 1.0}, {"name": "React", "confidence": 0.9}],
    "location": {"city": "SF", "region": "CA", "country": "US"},
    "links": {"linkedin": "https://linkedin.com/in/bob", "github": None},
}


# ----------------------------- path resolver -------------------------------
@pytest.mark.parametrize("path,expected", [
    ("emails[0]", "a@x.com"),
    ("emails[1]", "b@y.com"),
    ("emails[-1]", "b@y.com"),
    ("phones[0]", "+14155550100"),
    ("location.country", "US"),
    ("location.city", "SF"),
    ("links.linkedin", "https://linkedin.com/in/bob"),
    ("skills[].name", ["Python", "React"]),
])
def test_resolve_path_hits(path, expected):
    assert resolve_path(DATA, path) == expected


@pytest.mark.parametrize("path", [
    "emails[99]", "location.zipcode", "nonexistent", "skills[].missing",
    "emails[0].name",
])
def test_resolve_path_misses(path):
    result = resolve_path(DATA, path)
    assert result is _MISSING or result == []


def test_resolve_path_null_value_is_not_missing():
    assert resolve_path(DATA, "links.github") is None  # present but null


# ----------------------------- projection ----------------------------------
def _bob():
    raw = RawRecord(source="ats_json", full_name="Robert Smith",
                    emails=["bob@example.com"], phones=["+1-415-555-0100"],
                    skills=["Python", "reactjs"],
                    location={"city": "SF", "region": "CA", "country": "USA"},
                    links={"linkedin": "https://linkedin.com/in/bob"})
    return merge_records([raw])[0]


def test_project_select_subset():
    out = project(_bob(), {"fields": [{"path": "full_name", "type": "string"}]})
    assert set(out.keys()) == {"full_name"}


def test_project_rename_via_from():
    out = project(_bob(), {"fields": [{"path": "primary_email", "from": "emails[0]"}]})
    assert out["primary_email"] == "bob@example.com"


@pytest.mark.parametrize("kind,frm,expected", [
    ("E164", "phones[0]", "+14155550100"),
    ("lower", "full_name", "robert smith"),
    ("upper", "full_name", "ROBERT SMITH"),
])
def test_project_normalize_scalar(kind, frm, expected):
    out = project(_bob(), {"fields": [{"path": "v", "from": frm, "normalize": kind}]})
    assert out["v"] == expected


def test_project_normalize_canonical_list():
    out = project(_bob(), {"fields": [{"path": "skills", "from": "skills[].name", "normalize": "canonical"}]})
    assert out["skills"] == ["Python", "React"]


def test_project_on_missing_null():
    out = project(_bob(), {"fields": [{"path": "x", "from": "nope"}], "on_missing": "null"})
    assert out["x"] is None


def test_project_on_missing_omit():
    out = project(_bob(), {"fields": [{"path": "x", "from": "nope"}], "on_missing": "omit"})
    assert "x" not in out


def test_project_on_missing_error():
    with pytest.raises(ProjectionError):
        project(_bob(), {"fields": [{"path": "x", "from": "nope", "required": True}],
                         "on_missing": "error"})


def test_project_include_confidence_flag():
    cfg = {"fields": [{"path": "full_name"}], "include_confidence": True}
    assert "overall_confidence" in project(_bob(), cfg)


def test_project_include_provenance_flag():
    cfg = {"fields": [{"path": "full_name"}], "include_provenance": True}
    assert "provenance" in project(_bob(), cfg)


def test_project_default_schema_when_no_fields():
    out = project(_bob(), {})
    assert "candidate_id" in out and "provenance" in out


def test_project_default_can_drop_meta():
    out = project(_bob(), {"include_provenance": False, "include_confidence": False})
    assert "provenance" not in out and "overall_confidence" not in out


# ----------------------------- validation ----------------------------------
@pytest.mark.parametrize("value,decl,ok", [
    ("hello", "string", True),
    (5, "number", True),
    (5.5, "number", True),
    (True, "boolean", True),
    ({"a": 1}, "object", True),
    (["a", "b"], "string[]", True),
    ([1, 2], "number[]", True),
    ([{"a": 1}], "object[]", True),
    (5, "string", False),
    ("x", "number", False),
    (1, "boolean", False),
    ("x", "string[]", False),
    (["a", 1], "string[]", False),
    ([1, "a"], "number[]", False),
])
def test_validation_types(value, decl, ok):
    errs = validate_output({"f": value}, {"fields": [{"path": "f", "type": decl}]})
    assert (errs == []) == ok


def test_validation_required_missing():
    errs = validate_output({}, {"fields": [{"path": "f", "type": "string", "required": True}]})
    assert any("missing or null" in e for e in errs)


def test_validation_required_null():
    errs = validate_output({"f": None}, {"fields": [{"path": "f", "required": True}]})
    assert errs


def test_validation_unknown_type():
    errs = validate_output({"f": "x"}, {"fields": [{"path": "f", "type": "weird"}]})
    assert any("unknown type" in e for e in errs)


def test_validation_default_schema_no_errors():
    assert validate_output({"anything": 1}, {}) == []


def test_validation_optional_missing_is_ok():
    assert validate_output({}, {"fields": [{"path": "f", "type": "string"}]}) == []
