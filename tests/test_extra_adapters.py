"""Coverage for the source adapters (CSV, ATS JSON, resume)."""
import pytest

from transformer.adapters import csv_recruiter, ats_json, resume_text


# ----------------------------- CSV -----------------------------------------
def test_csv_basic():
    recs = csv_recruiter.parse("name,email,phone\nBob,bob@x.com,4155550100\n")
    assert len(recs) == 1
    assert recs[0].full_name == "Bob"
    assert recs[0].emails == ["bob@x.com"]
    assert recs[0].phones == ["4155550100"]


def test_csv_header_variants():
    text = "Full Name,E-mail,Phone Number,Employer,Role\nA,a@x.com,123,Acme,Eng\n"
    recs = csv_recruiter.parse(text)
    assert recs[0].full_name == "A"
    assert recs[0].emails == ["a@x.com"]
    assert recs[0].headline == "Eng"
    assert recs[0].experience[0]["company"] == "Acme"


def test_csv_empty_rows_dropped():
    recs = csv_recruiter.parse("name,email\n,\nBob,bob@x.com\n,\n")
    assert len(recs) == 1


def test_csv_empty_text():
    assert csv_recruiter.parse("") == []


def test_csv_unknown_columns_ignored():
    recs = csv_recruiter.parse("name,favorite_color\nBob,blue\n")
    assert recs[0].full_name == "Bob"


def test_csv_missing_file_returns_empty():
    assert csv_recruiter.parse_file("does/not/exist.csv") == []


def test_csv_title_becomes_headline_and_experience():
    recs = csv_recruiter.parse("name,title,current_company\nBob,Staff Engineer,Acme\n")
    assert recs[0].headline == "Staff Engineer"
    assert recs[0].experience[0]["title"] == "Staff Engineer"


# ----------------------------- ATS JSON ------------------------------------
def test_ats_single_object():
    recs = ats_json.parse('{"full_name":"Bob","email":"bob@x.com"}')
    assert len(recs) == 1
    assert recs[0].full_name == "Bob"


def test_ats_list_of_objects():
    recs = ats_json.parse('[{"name":"A","email":"a@x.com"},{"name":"B","email":"b@y.com"}]')
    assert len(recs) == 2


def test_ats_firstname_lastname_combine():
    recs = ats_json.parse('{"firstName":"Robert","lastName":"Smith","email":"r@x.com"}')
    assert recs[0].full_name == "Robert Smith"


@pytest.mark.parametrize("field,key", [
    ("email", "emailAddress"),
    ("phone", "phoneNumber"),
])
def test_ats_field_name_variants(field, key):
    recs = ats_json.parse('{"name":"Bob","%s":"value-here"}' % key)
    assert recs  # remap recognized the alias and produced a record


def test_ats_nested_location():
    recs = ats_json.parse('{"name":"Bob","address":{"city":"SF","state":"CA","country":"USA"}}')
    loc = recs[0].location
    assert loc["city"] == "SF" and loc["country"] == "USA"


@pytest.mark.parametrize("skills_key", ["skills", "skill_set", "competencies", "tags"])
def test_ats_skills_variants(skills_key):
    recs = ats_json.parse('{"name":"Bob","%s":["Python","AWS"]}' % skills_key)
    assert recs[0].skills == ["Python", "AWS"]


def test_ats_garbage_record_dropped():
    recs = ats_json.parse('{"unrelated":"junk","more":true}')
    assert recs == []


def test_ats_invalid_json_returns_empty():
    assert ats_json.parse("{not valid json") == []
    assert ats_json.parse("") == []


def test_ats_experience_mapping():
    recs = ats_json.parse(
        '{"name":"Bob","work_history":[{"employer":"Acme","role":"Eng","start_date":"2020","end_date":"2022"}]}')
    exp = recs[0].experience[0]
    assert exp["company"] == "Acme" and exp["title"] == "Eng"
    assert exp["start"] == "2020" and exp["end"] == "2022"


def test_ats_education_mapping():
    recs = ats_json.parse(
        '{"name":"Bob","education":[{"school":"MIT","degree":"BS","major":"CS","graduation_year":"2019"}]}')
    edu = recs[0].education[0]
    assert edu["institution"] == "MIT" and edu["degree"] == "BS"
    assert edu["field"] == "CS" and edu["end_year"] == "2019"


def test_ats_years_experience_numeric():
    recs = ats_json.parse('{"name":"Bob","yearsExperience":8}')
    assert recs[0].years_experience == 8.0


# ----------------------------- Resume --------------------------------------
RESUME = """Robert Smith
bob@example.com | (415) 555-0100

Skills
Python, React.js, AWS, Docker

Experience
Staff Engineer at Acme    Jan 2021 - Present
- Led the platform team.

Education
B.S. Computer Science, Stanford University, 2018
"""


def test_resume_name_guess():
    assert resume_text.parse(RESUME)[0].full_name == "Robert Smith"


def test_resume_emails_and_phones():
    rec = resume_text.parse(RESUME)[0]
    assert "bob@example.com" in rec.emails
    assert any("415" in p for p in rec.phones)


def test_resume_skills_section():
    rec = resume_text.parse(RESUME)[0]
    assert "Python" in rec.skills and "AWS" in rec.skills


def test_resume_experience_parsed():
    rec = resume_text.parse(RESUME)[0]
    assert rec.experience and rec.experience[0]["company"] == "Acme"


def test_resume_education_parsed():
    rec = resume_text.parse(RESUME)[0]
    assert rec.education and "Stanford" in rec.education[0]["institution"]


def test_resume_empty_text():
    assert resume_text.parse("") == []
    assert resume_text.parse("   \n  ") == []
