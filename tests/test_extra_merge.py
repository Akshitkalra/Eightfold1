"""Deeper coverage for clustering, conflict resolution, confidence, provenance."""
from transformer.canonical import RawRecord
from transformer.merge import merge_records, normalize_record, cluster


def R(**kw):
    return RawRecord(source=kw.pop("source", "recruiter_csv"), **kw)


# ----------------------------- clustering ----------------------------------
def test_cluster_by_shared_email():
    out = merge_records([
        R(source="recruiter_csv", full_name="Bob", emails=["x@y.com"]),
        R(source="ats_json", full_name="Robert", emails=["x@y.com"]),
    ])
    assert len(out) == 1


def test_cluster_by_shared_phone():
    out = merge_records([
        R(source="recruiter_csv", full_name="Bob", phones=["(415) 555-0100"]),
        R(source="ats_json", full_name="Robert", phones=["+1 415 555 0100"]),
    ])
    assert len(out) == 1


def test_cluster_by_github_url():
    out = merge_records([
        R(source="github", full_name="Bob", links={"github": "https://github.com/bob"}),
        R(source="resume", full_name="Bob", links={"github": "http://www.github.com/bob/"}),
    ])
    assert len(out) == 1  # url normalized (scheme/www/trailing slash)


def test_distinct_emails_not_merged():
    out = merge_records([
        R(full_name="Bob", emails=["a@x.com"]),
        R(full_name="Bob", emails=["b@y.com"]),
    ])
    assert len(out) == 2


def test_transitive_merge_via_chain():
    # A shares email with B; B shares phone with C -> all one cluster.
    out = merge_records([
        R(source="recruiter_csv", full_name="A", emails=["s@x.com"]),
        R(source="ats_json", full_name="B", emails=["s@x.com"], phones=["4155550100"]),
        R(source="resume", full_name="C", phones=["(415) 555-0100"]),
    ])
    assert len(out) == 1


def test_name_only_records_merge_by_name():
    out = merge_records([
        R(source="recruiter_csv", full_name="Jane Doe"),
        R(source="resume", full_name="Jane Doe"),
    ])
    assert len(out) == 1  # no strong keys -> weak name key links them


# ----------------------------- conflict resolution -------------------------
def test_name_conflict_ats_beats_csv():
    out = merge_records([
        R(source="recruiter_csv", full_name="Bob", emails=["x@y.com"]),
        R(source="ats_json", full_name="Robert Smith", emails=["x@y.com"]),
    ])
    assert out[0].full_name == "Robert Smith"


def test_name_conflict_resume_loses_to_csv():
    out = merge_records([
        R(source="recruiter_csv", full_name="Robert Smith", emails=["x@y.com"]),
        R(source="resume", full_name="Bob", emails=["x@y.com"]),
    ])
    assert out[0].full_name == "Robert Smith"


def test_emails_unioned_across_sources():
    out = merge_records([
        R(source="recruiter_csv", full_name="Bob", emails=["a@x.com"], phones=["4155550100"]),
        R(source="ats_json", full_name="Bob", emails=["b@y.com"], phones=["4155550100"]),
    ])
    assert set(out[0].emails) == {"a@x.com", "b@y.com"}


def test_location_picks_most_complete():
    out = merge_records([
        R(source="resume", full_name="Bob", emails=["x@y.com"],
          location={"city": "SF", "region": None, "country": None}),
        R(source="ats_json", full_name="Bob", emails=["x@y.com"],
          location={"city": "San Francisco", "region": "CA", "country": "USA"}),
    ])
    assert out[0].location["country"] == "US"
    assert out[0].location["region"] == "CA"


def test_years_experience_conflict_higher_trust_wins():
    out = merge_records([
        R(source="resume", full_name="Bob", emails=["x@y.com"], years_experience=5),
        R(source="ats_json", full_name="Bob", emails=["x@y.com"], years_experience=8),
    ])
    assert out[0].years_experience == 8.0


# ----------------------------- skills & confidence -------------------------
def test_skill_agreement_boosts_confidence():
    out = merge_records([
        R(source="ats_json", full_name="Bob", emails=["x@y.com"], skills=["Python"]),
        R(source="resume", full_name="Bob", emails=["x@y.com"], skills=["python"]),
    ])
    py = [s for s in out[0].skills if s.name == "Python"][0]
    assert set(py.sources) == {"ats_json", "resume"}
    assert py.confidence >= 0.9


def test_unknown_skill_lower_confidence_than_known():
    out = merge_records([
        R(source="ats_json", full_name="Bob", emails=["x@y.com"], skills=["Python", "rustlang"]),
    ])
    by = {s.name: s for s in out[0].skills}
    assert by["Python"].confidence > by["rustlang"].confidence


def test_overall_confidence_in_unit_range():
    out = merge_records([R(source="ats_json", full_name="Bob", emails=["x@y.com"])])
    assert 0.0 <= out[0].overall_confidence <= 1.0


# ----------------------------- provenance & id -----------------------------
def test_provenance_records_winning_source_on_conflict():
    # Names conflict -> winner comes from ONE source -> method "direct".
    out = merge_records([
        R(source="recruiter_csv", full_name="Bob", emails=["x@y.com"]),
        R(source="ats_json", full_name="Robert", emails=["x@y.com"]),
    ])
    name_prov = [p for p in out[0].provenance if p.field == "full_name"][0]
    assert name_prov.source == "ats_json"
    assert name_prov.method == "direct"


def test_provenance_merged_when_sources_agree():
    # Both sources agree on the same name -> method "merged".
    out = merge_records([
        R(source="recruiter_csv", full_name="Robert Smith", emails=["x@y.com"]),
        R(source="ats_json", full_name="Robert Smith", emails=["x@y.com"]),
    ])
    name_prov = [p for p in out[0].provenance if p.field == "full_name"][0]
    assert name_prov.method == "merged"


def test_candidate_id_deterministic_by_email():
    a = merge_records([R(full_name="Bob", emails=["x@y.com"])])[0]
    b = merge_records([R(full_name="Different", emails=["x@y.com"])])[0]
    assert a.candidate_id == b.candidate_id  # same strongest key -> same id


def test_candidate_id_changes_with_identity():
    a = merge_records([R(full_name="Bob", emails=["a@x.com"])])[0]
    b = merge_records([R(full_name="Bob", emails=["b@y.com"])])[0]
    assert a.candidate_id != b.candidate_id


# ----------------------------- robustness ----------------------------------
def test_empty_input_yields_no_profiles():
    assert merge_records([]) == []


def test_identityless_records_dropped():
    out = merge_records([R(source="recruiter_csv", emails=["not-an-email"])])
    assert out == []


def test_output_sorted_by_candidate_id():
    out = merge_records([
        R(full_name="Z", emails=["z@x.com"]),
        R(full_name="A", emails=["a@x.com"]),
    ])
    ids = [c.candidate_id for c in out]
    assert ids == sorted(ids)


def test_normalize_record_applies_all_normalizers():
    n = normalize_record(R(source="ats_json", full_name="  Bob   Smith ",
                           emails=["BOB@X.COM"], phones=["(415) 555-0100"],
                           skills=["reactjs"], location={"city": None, "region": None, "country": "USA"}))
    assert n.full_name == "Bob Smith"
    assert n.emails == ["bob@x.com"]
    assert n.phones == ["+14155550100"]
    assert n.skills == ["React"]
    assert n.location["country"] == "US"
