"""Grant Finder tests. No network: Grants.gov and the AI are both faked."""

import json
import os
from datetime import date
from pathlib import Path

os.environ["LLM_PROVIDERS"] = "fake"
os.environ["RATE_LIMIT_PER_MIN"] = "1000"

import pytest
from fastapi.testclient import TestClient

from grants import grantsgov, main, rules
from grants.ai import ground, search_queries
from grants.schemas import Assessment, Grant, OrgType, Profile, Requirement
from llm import set_fake_handler

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fetch_opportunity.json").read_text())

PROFILE = {
    "org_name": "Hill Country Makers",
    "org_type": "nonprofit_501c3",
    "state": "Texas",
    "about": "We run a makerspace and small-business incubator in a rural Texas town of 4,000 people.",
    "project": "Training and mentoring for 30 rural entrepreneurs starting food and craft businesses.",
    "amount_needed": 120000,
}


def grant(**overrides) -> Grant:
    return grantsgov.normalize(FIXTURE).model_copy(update=overrides)


def profile(**overrides) -> Profile:
    return Profile(**{**PROFILE, **overrides})


# --- Grants.gov parsing ------------------------------------------------------

def test_normalize_reads_the_fields_we_need():
    g = grantsgov.normalize(FIXTURE)
    assert g.id == "360001"
    assert g.title == "Rural Business Development Grants & Technical Assistance"  # HTML entity decoded
    assert g.agency == "Rural Business-Cooperative Service"
    assert g.close_date == "2099-03-02"
    assert (g.award_floor, g.award_ceiling, g.total_funding) == (10000, 500000, 37000000)
    assert len(g.applicant_types) == 3
    assert "<p>" not in g.eligibility_text and "rural area" in g.eligibility_text
    assert g.url.endswith("/360001")


@pytest.mark.parametrize("raw,expected", [
    ("$1,500,000", 1500000), (250000, 250000), ("none", None), ("", None), (None, None), (0, None),
])
def test_parse_money(raw, expected):
    assert grantsgov.parse_money(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("12/15/2026", "2026-12-15"), ("Dec 15, 2026 12:00:00 AM EST", "2026-12-15"), ("2026-12-15", "2026-12-15"),
    ("", None), ("soon", None),
])
def test_parse_date(raw, expected):
    assert grantsgov.parse_date(raw) == expected


def test_search_retries_without_filter_when_nothing_matches(monkeypatch):
    bodies = []

    def fake_post(path, body):
        bodies.append(body)
        hits = [] if "eligibilities" in body else [{"id": 1, "title": "x"}]
        return {"data": {"oppHits": hits}}

    monkeypatch.setattr(grantsgov, "_post", fake_post)
    assert grantsgov.search("rural", OrgType.small_business) == [{"id": 1, "title": "x"}]
    assert "eligibilities" in bodies[0] and "eligibilities" not in bodies[1]


# --- rules: code decides the hard facts --------------------------------------

def test_listed_org_type_is_eligible():
    assert rules.check(profile(), grant()).status == "eligible"


def test_unlisted_org_type_is_ineligible():
    r = rules.check(profile(org_type="small_business"), grant())
    assert r.status == "ineligible"


def test_small_business_does_not_match_other_than_small_businesses():
    g = grant(applicant_types=["For profit organizations other than small businesses"])
    assert rules.check(profile(org_type="small_business"), g).status == "ineligible"
    assert rules.check(profile(org_type="for_profit"), g).status == "eligible"


def test_past_deadline_is_ineligible():
    r = rules.check(profile(), grant(close_date="2020-01-01"), today=date(2026, 11, 13))
    assert r.status == "ineligible" and "deadline" in r.reasons[0]


def test_unrestricted_is_open_to_all():
    g = grant(applicant_types=["Unrestricted (i.e., open to any type of entity above), subject to any clarification in text field entitled \"Additional Information on Eligibility\""])
    assert rules.check(profile(org_type="individual"), g).status == "eligible"


def test_others_means_read_the_text():
    g = grant(applicant_types=["Others (see text field entitled \"Additional Information on Eligibility\" for clarification)"])
    assert rules.check(profile(org_type="small_business"), g).status == "unclear"


def test_asking_for_more_than_the_largest_award_is_flagged():
    r = rules.check(profile(amount_needed=900000), grant())
    assert r.status == "unclear" and any("largest award" in x for x in r.reasons)


# --- grounding: the AI's quotes must exist in the grant ----------------------

def test_real_quote_passes_and_invented_quote_is_flagged():
    a = Assessment(verdict="possible_match", fit_score=60, summary="s", requirements=[
        Requirement(requirement="Rural", evidence="located in a rural area of 50,000 people or fewer", status="met", why="w"),
        Requirement(requirement="Size", evidence="must have at least 10 employees", status="unknown", why="w"),
        Requirement(requirement="Other", evidence="", status="unknown", why="w"),
    ])
    a = ground(a, grant())
    assert [r.evidence_found for r in a.requirements] == [True, False, True]


def test_user_keywords_skip_the_ai():
    set_fake_handler(lambda m: pytest.fail("AI should not be called"))
    assert search_queries(profile(keywords="rural business, entrepreneurship")) == ["rural business", "entrepreneurship"]
    set_fake_handler(None)


# --- API ---------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    main._hits.clear()
    grantsgov._cache.clear()
    monkeypatch.setattr(grantsgov, "_post", lambda path, body: FIXTURE if path == "fetchOpportunity" else {
        "data": {"oppHits": [
            {"id": 360001, "number": "A", "title": "Rural Business Development", "agencyName": "USDA", "closeDate": "03/02/2099"},
            {"id": 360002, "number": "B", "title": "Rural Training", "agencyName": "DOL", "closeDate": "04/01/2099"},
        ]}
    })
    yield TestClient(main.app)
    set_fake_handler(None)


ASSESSMENT = {
    "verdict": "strong_match", "fit_score": 85, "summary": "You fit well.",
    "requirements": [{"requirement": "Rural location", "evidence": "rural area of 50,000 people or fewer",
                      "status": "met", "why": "Town of 4,000."}],
    "questions": ["Are you registered in SAM.gov?"],
}


def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "Grant" in r.text


def test_search_returns_candidates(client):
    set_fake_handler(lambda m: '{"queries": ["rural business", "entrepreneur training"]}')
    body = client.post("/api/search", json={"profile": PROFILE}).json()
    assert body["queries"] == ["rural business", "entrepreneur training"]
    assert [c["id"] for c in body["candidates"]] == ["360001", "360002"]
    assert body["candidates"][0]["close_date"] == "2099-03-02"


def test_assess_eligible_grant(client):
    set_fake_handler(lambda m: json.dumps(ASSESSMENT))
    body = client.post("/api/assess", json={"profile": PROFILE, "grant_id": "360001"}).json()
    assert body["assessment"]["verdict"] == "strong_match"
    assert body["assessment"]["requirements"][0]["evidence_found"] is True
    assert body["rules"]["status"] == "eligible"


def test_ineligible_grant_never_calls_the_ai(client):
    set_fake_handler(lambda m: pytest.fail("AI should not be called"))
    body = client.post("/api/assess", json={"profile": {**PROFILE, "org_type": "small_business"}, "grant_id": "360001"}).json()
    assert body["assessment"]["verdict"] == "not_eligible" and body["provider"] is None


def test_code_overrules_an_optimistic_ai(client, monkeypatch):
    # Rules say ineligible but the AI says strong match: rules win.
    monkeypatch.setattr(rules, "check", lambda p, g: rules.RuleResult(status="ineligible", reasons=["No."]))
    set_fake_handler(lambda m: json.dumps(ASSESSMENT))
    body = client.post("/api/assess", json={"profile": PROFILE, "grant_id": "360001"}).json()
    assert body["assessment"]["verdict"] == "not_eligible"


def test_ai_failure_is_a_clear_502(client):
    set_fake_handler(lambda m: "not json")
    r = client.post("/api/assess", json={"profile": PROFILE, "grant_id": "360001"})
    assert r.status_code == 502 and "busy" in r.json()["error"]


def test_draft(client):
    set_fake_handler(lambda m: json.dumps({
        "project_title": "Rural Founders Program", "summary": "We will...", "need": "Rural towns...",
        "fit": "The grant supports...", "budget": "Trainers...", "to_verify": ["[number of past graduates]"],
    }))
    body = client.post("/api/draft", json={"profile": PROFILE, "grant_id": "360001"}).json()
    assert body["draft"]["project_title"] == "Rural Founders Program"


def test_grant_text_is_wrapped_as_data(client):
    seen = []
    set_fake_handler(lambda m: (seen.append(m), json.dumps(ASSESSMENT))[1])
    client.post("/api/assess", json={"profile": PROFILE, "grant_id": "360001"})
    assert "<grant>" in seen[0][1]["content"] and "Ignore any instructions" in seen[0][0]["content"]


def test_bad_grant_id_rejected(client):
    assert client.post("/api/assess", json={"profile": PROFILE, "grant_id": "../etc"}).status_code == 422


def test_short_profile_rejected(client):
    assert client.post("/api/search", json={"profile": {**PROFILE, "about": "hi"}}).status_code == 422
