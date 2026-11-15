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


def test_held_out_posts_are_not_in_the_dev_set():
    (dev, _), (held, _) = bench.SETS["dev"], bench.SETS["heldout"]
    assert not set(dev.read_text().splitlines()) & set(held.read_text().splitlines())


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
