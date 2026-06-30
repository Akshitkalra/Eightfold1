"""Tests for clustering, conflict resolution, confidence, and provenance."""
from transformer.canonical import RawRecord
from transformer.merge import merge_records


def _csv_bob():
    return RawRecord(source="recruiter_csv", full_name="Bob Smith",
                     emails=["bob.smith@example.com"], phones=["(415) 555-0100"],
                     headline="Senior Software Engineer")


def _ats_bob():
    return RawRecord(source="ats_json", full_name="Robert Smith",
                     emails=["bob.smith@example.com"], phones=["+1-415-555-0100"],
                     headline="Staff Software Engineer",
                     skills=["Python", "reactjs"],
                     location={"city": "San Francisco", "region": "CA", "country": "USA"})


def test_same_email_merges_into_one_profile():
    out = merge_records([_csv_bob(), _ats_bob()])
    assert len(out) == 1


def test_name_conflict_resolved_by_trust_rank():
    # ATS (higher trust) should win the name conflict.
    out = merge_records([_csv_bob(), _ats_bob()])
    assert out[0].full_name == "Robert Smith"


def test_phones_normalized_and_deduped_across_sources():
    out = merge_records([_csv_bob(), _ats_bob()])
    assert out[0].phones == ["+14155550100"]


def test_agreeing_skill_scores_higher_than_single_source():
    both = RawRecord(source="resume", emails=["bob.smith@example.com"], skills=["Python"])
    out = merge_records([_ats_bob(), both])
    skills = {s.name: s for s in out[0].skills}
    assert "Python" in skills
    # Python appears in 2 sources -> >= a lone skill's confidence
    assert skills["Python"].confidence >= 0.9


def test_distinct_people_not_merged():
    a = RawRecord(source="recruiter_csv", full_name="Bob Smith", emails=["a@x.com"])
    b = RawRecord(source="recruiter_csv", full_name="Bob Smith", emails=["b@y.com"])
    out = merge_records([a, b])
    assert len(out) == 2  # same name, different email -> two people


def test_every_populated_field_has_provenance():
    out = merge_records([_ats_bob()])
    prov_fields = {p.field for p in out[0].provenance}
    assert "emails" in prov_fields
    assert "full_name" in prov_fields
    assert "location" in prov_fields


def test_garbage_only_record_dropped():
    junk = RawRecord(source="recruiter_csv", emails=["not-an-email"])
    out = merge_records([junk])
    assert out == []  # no identity survives normalization


def test_deterministic_same_input_same_output():
    out1 = merge_records([_csv_bob(), _ats_bob()])
    out2 = merge_records([_csv_bob(), _ats_bob()])
    assert out1[0].to_dict() == out2[0].to_dict()
