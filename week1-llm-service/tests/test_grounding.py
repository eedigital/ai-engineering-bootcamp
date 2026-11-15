"""Salary grounding: a misread end of the range is replaced by the number written in the post."""

import json

import pytest

from app.grounding import fix_salary, ranges

YEN = "Backend Engineer (Go) — Tokyo. ¥8,000,000–¥11,000,000 per year. Hybrid. Business-level Japanese required."


@pytest.mark.parametrize("text,expected", [
    ("¥8,000,000–¥11,000,000 per year", (8_000_000, 11_000_000)),
    ("€70-85k", (70_000, 85_000)),
    ("$150-180k + equity", (150_000, 180_000)),
    ("₹25 LPA - ₹35 LPA", (2_500_000, 3_500_000)),
    ("95.000 - 120.000 EUR", (95_000, 120_000)),
    ("£55,000 to £65,000 DOE", (55_000, 65_000)),
    ("CAD 52,000 to 58,000", (52_000, 58_000)),
])
def test_ranges_read_every_format(text, expected):
    assert expected in ranges(text)


def test_misread_end_is_fixed_from_the_post():
    # Found in the held-out benchmark: the model returned 10,000,000 for ¥11,000,000
    assert fix_salary(8_000_000, 10_000_000, YEN) == (8_000_000, 11_000_000, True)
    assert fix_salary(7_000_000, 11_000_000, YEN) == (8_000_000, 11_000_000, True)


def test_correct_answers_are_left_alone():
    assert fix_salary(8_000_000, 11_000_000, YEN) == (8_000_000, 11_000_000, False)
    assert fix_salary(None, 210_000, "Up to $210,000") == (None, 210_000, False)


def test_nothing_is_invented_when_neither_end_matches():
    # e.g. an hourly rate the model converted to a yearly figure: no range end matches, so it's left as is
    assert fix_salary(58_240, 66_560, "$28-32/hour") == (58_240, 66_560, False)


def test_the_api_reports_a_correction(client, fake_llm):
    fake_llm(json.dumps({"title": "Backend Engineer", "location": "Tokyo", "work_mode": "hybrid", "seniority": "unknown",
                         "salary_min": 8000000, "salary_max": 10000000, "currency": "JPY", "skills": ["Go"]}))
    body = client.post("/extract", json={"text": YEN}).json()
    assert body["ok"] and body["data"]["salary_max"] == 11_000_000 and body["salary_corrected"] is True
