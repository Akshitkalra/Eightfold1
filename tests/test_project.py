"""Tests for the projection layer, path resolver, and validation."""
import pytest

from transformer.canonical import RawRecord
from transformer.merge import merge_records
from transformer.project import project, resolve_path, ProjectionError
from transformer.validate import validate_output


def _bob():
    raw = RawRecord(source="ats_json", full_name="Robert Smith",
                    emails=["bob@example.com"], phones=["+1-415-555-0100"],
                    skills=["Python", "reactjs"],
                    location={"city": "SF", "region": "CA", "country": "USA"},
                    links={"linkedin": "https://linkedin.com/in/bob"})
    return merge_records([raw])[0]


def test_path_resolver_index_and_list_projection():
    data = {"emails": ["a@x.com", "b@y.com"],
            "skills": [{"name": "Python"}, {"name": "React"}],
            "location": {"country": "US"}}
    assert resolve_path(data, "emails[0]") == "a@x.com"
    assert resolve_path(data, "location.country") == "US"
    assert resolve_path(data, "skills[].name") == ["Python", "React"]


def test_projection_renames_and_normalizes():
    cfg = {
        "fields": [
            {"path": "full_name", "type": "string", "required": True},
            {"path": "primary_email", "from": "emails[0]", "type": "string"},
            {"path": "phone", "from": "phones[0]", "normalize": "E164"},
            {"path": "skills", "from": "skills[].name", "type": "string[]"},
        ],
        "include_confidence": True,
    }
    out = project(_bob(), cfg)
    assert out["primary_email"] == "bob@example.com"
    assert out["phone"] == "+14155550100"
    assert out["skills"] == ["Python", "React"]
    assert "overall_confidence" in out
    assert "provenance" not in out  # not requested


def test_on_missing_null_vs_omit_vs_error():
    base = {"fields": [{"path": "nickname", "from": "does.not.exist", "required": True}]}

    out_null = project(_bob(), {**base, "on_missing": "null"})
    assert out_null["nickname"] is None

    out_omit = project(_bob(), {**base, "on_missing": "omit"})
    assert "nickname" not in out_omit

    with pytest.raises(ProjectionError):
        project(_bob(), {**base, "on_missing": "error"})


def test_validation_catches_type_and_required():
    cfg = {"fields": [
        {"path": "full_name", "type": "string", "required": True},
        {"path": "skills", "type": "string[]"},
    ]}
    good = {"full_name": "Robert Smith", "skills": ["Python"]}
    assert validate_output(good, cfg) == []

    bad = {"full_name": None, "skills": "not-a-list"}
    errs = validate_output(bad, cfg)
    assert any("full_name" in e for e in errs)
    assert any("skills" in e for e in errs)


def test_default_schema_when_no_fields():
    out = project(_bob(), {})
    assert "candidate_id" in out
    assert "provenance" in out
    assert isinstance(out["skills"], list)
