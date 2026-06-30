"""Unit tests for the deterministic normalizers."""
from transformer.normalize.phones import normalize_phone, normalize_phones
from transformer.normalize.dates import to_year_month, to_year
from transformer.normalize.country import normalize_country
from transformer.normalize.skills import canonical_skill, canonical_skills
from transformer.normalize.emails import normalize_email, extract_emails


def test_phone_formats_collapse_to_same_e164():
    assert normalize_phone("(415) 555-0100") == "+14155550100"
    assert normalize_phone("+1-415-555-0100") == "+14155550100"
    assert normalize_phone("4155550100") == "+14155550100"


def test_phone_garbage_returns_none_not_invented():
    assert normalize_phone("not a phone") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def test_phone_list_dedupes():
    assert normalize_phones(["(415) 555-0100", "+1 415 555 0100"]) == ["+14155550100"]


def test_dates_to_year_month():
    assert to_year_month("Jan 2021") == "2021-01"
    assert to_year_month("2020-3") == "2020-03"
    assert to_year_month("2019") == "2019-01"
    assert to_year_month("present") is None
    assert to_year_month("garbage") is None


def test_dates_to_year():
    assert to_year("class of 2019") == "2019"
    assert to_year("2018") == "2018"
    assert to_year("present") is None


def test_country_iso_alpha2():
    assert normalize_country("USA") == "US"
    assert normalize_country("United States") == "US"
    assert normalize_country("India") == "IN"
    assert normalize_country("uk") == "GB"
    assert normalize_country("US") == "US"
    assert normalize_country("zzzzz") is None


def test_skill_canonicalization_and_dedupe():
    assert canonical_skill("reactjs") == "React"
    assert canonical_skill("React.js") == "React"
    # three variants collapse to one; unknown kept verbatim
    assert canonical_skills(["reactjs", "React.js", "REACT", "rustlang"]) == ["React", "rustlang"]


def test_email_lowercase_validate_extract():
    assert normalize_email("Bob@X.COM") == "bob@x.com"
    assert normalize_email("not-an-email") is None
    assert extract_emails("reach a.b@c.io or junk@@") == ["a.b@c.io"]
