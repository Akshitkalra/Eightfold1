"""Broad parametrized coverage for the normalizers (~110 cases)."""
import pytest

from transformer.normalize.phones import normalize_phone, normalize_phones
from transformer.normalize.dates import to_year_month, to_year
from transformer.normalize.country import normalize_country
from transformer.normalize.skills import canonical_skill, canonical_skills, is_known
from transformer.normalize.emails import normalize_email, extract_emails


# ----------------------------- phones --------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("(415) 555-0100", "+14155550100"),
    ("+1-415-555-0100", "+14155550100"),
    ("4155550100", "+14155550100"),
    ("+1 (415) 555-0100", "+14155550100"),
    ("415.555.0100", "+14155550100"),
    ("+44 20 7946 0958", "+442079460958"),
    ("+91 98765 43210", "+919876543210"),
    ("+91-98765-43210", "+919876543210"),
])
def test_phone_valid(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ", None, "not a phone", "12345", "555-0100", "abcdefg", "++++",
])
def test_phone_invalid_returns_none(raw):
    assert normalize_phone(raw) is None


def test_phone_region_override_for_india():
    assert normalize_phone("9988776655", "IN") == "+919988776655"
    assert normalize_phone("9988776655", "US") is None  # invalid as US


def test_phones_list_dedupes_and_drops_bad():
    assert normalize_phones(["(415) 555-0100", "+1 415 555 0100", "garbage"]) == ["+14155550100"]


# ----------------------------- dates: year-month ---------------------------
@pytest.mark.parametrize("raw,expected", [
    ("Jan 2021", "2021-01"),
    ("January 2021", "2021-01"),
    ("2020-3", "2020-03"),
    ("2020-03", "2020-03"),
    ("2020-03-15", "2020-03"),
    ("2019", "2019-01"),
    ("Dec 2018", "2018-12"),
    ("Sep 2015", "2015-09"),
    ("present", None),
    ("current", None),
    ("now", None),
    ("garbage", None),
])
def test_to_year_month(raw, expected):
    assert to_year_month(raw) == expected


def test_to_year_month_empty():
    assert to_year_month("") is None
    assert to_year_month(None) is None


# ----------------------------- dates: year ---------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("2018", "2018"),
    ("class of 2019", "2019"),
    ("Graduated 2020", "2020"),
    ("May 2017", "2017"),
    ("2021", "2021"),
    ("present", None),
    ("garbage", None),
    ("", None),
])
def test_to_year(raw, expected):
    assert to_year(raw) == expected


# ----------------------------- country -------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("USA", "US"), ("United States", "US"), ("United States of America", "US"),
    ("America", "US"), ("us", "US"), ("US", "US"), ("USA ", "US"),
    ("India", "IN"), ("IN", "IN"), ("IND", "IN"), ("bharat", "IN"),
    ("uk", "GB"), ("United Kingdom", "GB"), ("England", "GB"),
    ("Britain", "GB"), ("Great Britain", "GB"),
    ("Germany", "DE"), ("DEU", "DE"), ("DE", "DE"),
    ("France", "FR"), ("FRA", "FR"),
    ("Canada", "CA"), ("CAN", "CA"),
    ("Australia", "AU"), ("Japan", "JP"), ("Brazil", "BR"),
    ("Singapore", "SG"), ("Netherlands", "NL"), ("Spain", "ES"),
    ("Italy", "IT"), ("China", "CN"), ("Mexico", "MX"),
    ("uae", "AE"), ("South Korea", "KR"), ("Russia", "RU"),
])
def test_country_valid(raw, expected):
    assert normalize_country(raw) == expected


@pytest.mark.parametrize("raw", ["zzzzz", "12345", "", None])
def test_country_invalid_returns_none(raw):
    assert normalize_country(raw) is None


# ----------------------------- skills --------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("reactjs", "React"), ("React.js", "React"), ("REACT", "React"), ("react", "React"),
    ("js", "JavaScript"), ("javascript", "JavaScript"), ("ECMAScript", "JavaScript"),
    ("py", "Python"), ("python", "Python"), ("Python3", "Python"), ("  Python  ", "Python"),
    ("k8s", "Kubernetes"), ("kubernetes", "Kubernetes"),
    ("postgres", "PostgreSQL"), ("postgresql", "PostgreSQL"), ("psql", "PostgreSQL"),
    ("node", "Node.js"), ("nodejs", "Node.js"), ("node.js", "Node.js"),
    ("aws", "AWS"), ("amazon web services", "AWS"),
    ("ml", "Machine Learning"), ("machine learning", "Machine Learning"),
    ("golang", "Go"), ("go", "Go"),
    ("c++", "C++"), ("cpp", "C++"), ("c#", "C#"), ("csharp", "C#"),
    ("tf", "TensorFlow"), ("tensorflow", "TensorFlow"),
    ("sklearn", "scikit-learn"), ("scikit-learn", "scikit-learn"),
    ("graphql", "GraphQL"), ("gcp", "GCP"), ("google cloud", "GCP"),
])
def test_skill_canonical(raw, expected):
    assert canonical_skill(raw) == expected


@pytest.mark.parametrize("raw", ["rustlang", "COBOL", "Solidity", "Elixir"])
def test_unknown_skill_kept_verbatim(raw):
    assert canonical_skill(raw) == raw


def test_skill_empty():
    assert canonical_skill("") is None
    assert canonical_skill(None) is None


def test_skills_list_dedupe_known_and_unknown():
    assert canonical_skills(["reactjs", "React.js", "REACT", "rustlang"]) == ["React", "rustlang"]
    assert canonical_skills(["py", "Python", "PYTHON"]) == ["Python"]


def test_is_known():
    assert is_known("reactjs") is True
    assert is_known("rustlang") is False


# ----------------------------- emails --------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("Bob@X.COM", "bob@x.com"),
    ("  a@b.io ", "a@b.io"),
    ("First.Last@Example.COM", "first.last@example.com"),
    ("x_y+z@a-b.co.uk", "x_y+z@a-b.co.uk"),
    ("user123@domain.org", "user123@domain.org"),
    ("a.b.c@d.e.f.com", "a.b.c@d.e.f.com"),
])
def test_email_valid(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", [
    "plainaddress", "@no-local.com", "no-at.com", "a@b", "a@.com",
    "a@b.", "", None, "two@@at.com",
])
def test_email_invalid_returns_none(raw):
    assert normalize_email(raw) is None


@pytest.mark.parametrize("text,expected", [
    ("reach a.b@c.io or junk@@", ["a.b@c.io"]),
    ("Contact: A@B.COM, c@d.org", ["a@b.com", "c@d.org"]),
    ("dup x@y.com and X@Y.COM", ["x@y.com"]),
    ("no emails here", []),
])
def test_extract_emails(text, expected):
    assert extract_emails(text) == expected
