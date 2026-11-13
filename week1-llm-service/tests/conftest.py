import os

# Tests never call a real model: the "fake" provider returns whatever the test sets.
os.environ["LLM_PROVIDERS"] = "fake"
os.environ["RATE_LIMIT_PER_MIN"] = "1000"

import pytest
from fastapi.testclient import TestClient

from app import main
from llm import set_fake_handler

GOOD_JSON = (
    '{"title": "Senior Backend Engineer", "company": "Acme", "location": "London", '
    '"work_mode": "hybrid", "seniority": "senior", "salary_min": 90000, "salary_max": 110000, '
    '"currency": "GBP", "skills": ["Python", "PostgreSQL", "python"]}'
)

POST = (
    "Acme is hiring a Senior Backend Engineer in London (hybrid, 3 days in office). "
    "Salary £90k-£110k. You'll work with Python and PostgreSQL."
)


@pytest.fixture
def client():
    main._hits.clear()
    yield TestClient(main.app)
    set_fake_handler(None)


@pytest.fixture
def fake_llm():
    """Register replies in order; the fixture records every message list sent."""
    calls: list[list[dict]] = []

    def use(*replies: str):
        it = iter(replies)

        def handler(messages):
            calls.append(messages)
            return next(it)

        set_fake_handler(handler)
        return calls

    return use
