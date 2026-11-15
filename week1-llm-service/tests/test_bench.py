"""The benchmark's scoring: what counts as a correct field."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bench", ROOT / "scripts" / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_every_sample_has_an_expected_answer_for_every_field():
    for posts_file, expected_file in bench.SETS.values():
        posts = [l for l in posts_file.read_text().splitlines() if l.strip()]
        expected = [json.loads(l) for l in expected_file.read_text().splitlines() if l.strip()]
        assert len(posts) == len(expected) and all(set(bench.FIELDS) <= set(e) for e in expected)


def test_the_sets_share_no_posts():
    files = [p for p, _ in bench.SETS.values()]
    lines = [set(f.read_text().splitlines()) for f in files]
    assert all(not (a & b) for i, a in enumerate(lines) for b in lines[i + 1:])


def test_text_fields_match_loosely():
    assert bench.field_ok("title", "Mid-level DevOps Engineer", "DevOps Engineer")
    assert bench.field_ok("location", "Austin, TX", "Austin")
    assert not bench.field_ok("company", "Initech", "Acme")


def test_lists_of_acceptable_answers_and_unscored_fields():
    assert bench.field_ok("seniority", "lead", ["senior", "lead"]) and not bench.field_ok("seniority", "junior", ["senior", "lead"])
    assert bench.field_ok("salary_min", None, [45, None]) and bench.field_ok("salary_min", 45, [45, None])
    assert bench.field_ok("company", "Anything", "*") is None


def test_null_expected_means_must_be_empty():
    assert bench.field_ok("currency", None, None) and not bench.field_ok("currency", "USD", None)


def test_numbers_must_match_exactly():
    assert bench.field_ok("salary_min", 90000, 90000) and not bench.field_ok("salary_min", 90, 90000)


def test_skills_need_every_expected_skill():
    assert bench.field_ok("skills", ["react", "NextJS", "TypeScript"], ["React", "Next.js"])
    assert not bench.field_ok("skills", ["React"], ["React", "Next.js"])


def test_score_a_whole_post():
    marks = bench.score({"title": "Senior Backend Engineer", "company": "Acme", "location": "London, UK", "work_mode": "hybrid",
                         "seniority": "senior", "salary_min": 90000, "salary_max": 110000, "currency": "GBP",
                         "skills": ["Python", "PostgreSQL", "AWS"]},
                        json.loads((ROOT / "samples" / "expected.jsonl").read_text().splitlines()[0]))
    assert all(marks.values())


def test_real_ad_answers_come_from_the_employer_data():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from real_ads import expected_for, text_of
    text = text_of("&lt;p&gt;Build things.&lt;/p&gt;&lt;p&gt;The base salary range is $150,000 - $180,000.&lt;/p&gt;")
    assert "&lt;" not in text and "$150,000" in text
    job = {"title": "Senior Engineer, Payments", "location": {"name": "San Francisco, CA; New York, NY"},
           "pay_input_ranges": [{"min_cents": 15000000, "max_cents": 18000000, "currency_type": "USD"},
                                {"min_cents": 99900000, "max_cents": 99990000, "currency_type": "USD"}]}
    e = expected_for(job, text)
    assert e["title"] == ["Senior Engineer, Payments", "Senior Engineer"]
    assert "San Francisco" in e["location"] and "New York, NY" in e["location"]
    assert e["salary_min"] == [150000] and e["salary_max"] == [180000]   # the range not written in the ad isn't scored
    assert e["seniority"] == "*" and e["skills"] == "*"


def test_real_ads_without_a_written_salary_dont_score_salary():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from real_ads import expected_for
    e = expected_for({"title": "Designer", "location": {"name": "Remote - US"}, "pay_input_ranges": []}, "No pay here.")
    assert e["salary_min"] == "*" and e["location"] == "*"



def test_real_ad_locations_are_split_and_placeholders_ignored():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from real_ads import _locations
    assert _locations("N/A") == "*" and _locations("US - Remote") == ["US"]
    assert "New York" in _locations("San Francisco, CA • New York, NY • United States")
    assert bench.field_ok("location", "US - Remote Eligible", ["United States"])
    assert not bench.field_ok("location", "Uruguay", ["US"])
