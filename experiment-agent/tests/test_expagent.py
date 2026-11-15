"""Experiment Designer: the maths, reading numbers, the plan, and the Linear agent flow (Linear's API faked)."""

import hashlib
import hmac
import json
import os
import time

os.environ["LLM_PROVIDERS"] = "fake"
os.environ["LLM_RATE_LIMIT_WAIT_S"] = "0"
os.environ["LINEAR_WEBHOOK_SECRET"] = "whsec_test"
os.environ["LINEAR_CLIENT_ID"] = "cid"
os.environ["LINEAR_CLIENT_SECRET"] = "csecret"

import pytest
from fastapi.testclient import TestClient

from expagent import design, linear, main, posthog, stats
from llm import set_fake_handler

ISSUE = ('<issue identifier="GRO-42"><title>Test shorter checkout</title><description>Cut checkout from 4 steps to 2. '
         'Checkout converts at 3.2% today, about 2,000 visitors a day. We want to detect a 10% lift.</description></issue>')


@pytest.fixture
def client():
    main._hits.clear()
    main.sessions.clear()
    main.seen = linear.Seen()
    yield TestClient(main.app)
    set_fake_handler(None)


@pytest.fixture
def linear_api(monkeypatch):
    """Record every GraphQL call instead of calling Linear."""
    calls = []

    def fake(query, variables=None, token=None):
        calls.append((query, variables or {}))
        if "agentSession(id" in query:
            return {"agentSession": {"issue": {"title": "Test shorter checkout", "description": "Converts at 3.2%."}}}
        return {"agentActivityCreate": {"success": True}}

    monkeypatch.setattr(linear, "graphql", fake)
    return calls


def contents(calls):
    return [v["input"]["content"] for q, v in calls if "agentActivityCreate" in q]


# --- maths ------------------------------------------------------------------------------------

@pytest.mark.parametrize("baseline,mde,expected", [(0.10, 0.20, 3841), (0.05, 0.10, 31234)])
def test_sample_size_matches_the_standard_formula(baseline, mde, expected):
    assert abs(stats.per_variant(baseline, mde) - expected) <= 2


def test_more_power_or_stricter_significance_needs_more_users():
    base = stats.per_variant(0.05, 0.10)
    assert stats.per_variant(0.05, 0.10, power=0.9) > base and stats.per_variant(0.05, 0.10, alpha=0.01) > base


def test_duration_rounds_up_to_full_weeks():
    p = stats.plan(0.032, 0.10, daily_traffic=2000)
    assert (p.per_variant, p.total, p.days, p.days_rounded) == (49777, 99554, 50, 56)
    assert stats.plan(0.5, 0.5, daily_traffic=10_000).days_rounded == 7  # never less than a week


def test_traffic_share_and_extra_variants_lengthen_the_test():
    p = stats.plan(0.05, 0.10, 5000)
    assert stats.plan(0.05, 0.10, 5000, traffic_share=0.5).days > p.days and stats.plan(0.05, 0.10, 5000, variants=3).days > p.days


@pytest.mark.parametrize("baseline,mde", [(0, 0.1), (1.2, 0.1), (0.05, 0), (0.6, 1.0)])
def test_impossible_inputs_are_refused(baseline, mde):
    with pytest.raises(ValueError):
        stats.per_variant(baseline, mde)


# --- reading numbers --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Checkout converts at 3.2% today, 2,000 visitors a day. Detect a 10% lift.", {"baseline": 0.032, "mde": 0.10, "daily_traffic": 2000}),
    ("baseline 2.4%, detect a 15% lift, 5,000 visitors a day", {"baseline": 0.024, "mde": 0.15, "daily_traffic": 5000}),
    ("conversion rate is 12%. MDE 1.5 percentage points. 42k users per week.", {"baseline": 0.12, "mde": 0.125, "daily_traffic": 6000}),
    ("Activation rate is 40%. Detect a 3 pp lift. 12k signups per month", {"baseline": 0.40, "mde": 0.075}),
    ("50% of traffic in the test, 3 variants, power 90%", {"traffic_share": 0.5, "variants": 3, "power": 0.9}),
])
def test_numbers_are_read_from_the_issue(text, expected):
    found = design.numbers(text)
    for k, v in expected.items():
        assert found[k] == pytest.approx(v, rel=1e-3), k


def test_nothing_stated_means_nothing_found():
    assert design.numbers("Test shorter checkout") == {}


# --- the plan ---------------------------------------------------------------------------------

def test_a_plan_from_the_issue_with_the_template():
    out = design.build(ISSUE, use_ai=False)
    md = out["markdown"]
    assert out["assumed"] == [] and "**49,777**" in md and "56 days (8 full weeks)" in md
    assert "If we ship a shorter checkout" in md and "### Guardrail metrics" in md and "```sql" in md
    assert "template, the AI was unavailable" in md


def test_missing_numbers_are_assumed_and_said():
    out = design.build("Test a new pricing page", use_ai=False)
    assert set(out["assumed"]) == {"baseline", "mde", "daily_traffic"}
    assert "*(assumed)*" in out["markdown"] and "Reply with your numbers" in out["markdown"]


def test_a_reply_overrides_the_issue():
    out = design.build(ISSUE, "Actually baseline is 6% and we only need to detect a 20% lift", use_ai=False)
    assert out["plan"].baseline == 0.06 and out["plan"].mde_relative == 0.20


def test_very_long_tests_get_options():
    assert "longer than 8 weeks" in design.build("Test X. Baseline 1%, detect a 5% lift, 500 visitors a day", use_ai=False)["markdown"]


def test_the_ai_writes_the_words_but_not_the_numbers():
    set_fake_handler(lambda m: json.dumps({
        "hypothesis": "If we cut checkout to 2 steps, then checkout completion will rise because fewer people drop off at shipping.",
        "primary_metric": "Checkout completion rate", "conversion_event": "Order Completed", "exposure_event": "checkout started",
        "flag_key": "Short Checkout!", "guardrails": ["Average order value", "Payment errors", "Refund rate"],
        "risks": [], "questions": []}))
    out = design.build(ISSUE)
    assert out["words_source"] == "fake" and out["plan"].per_variant == 49777
    assert out["words"].conversion_event == "order_completed" and out["words"].flag_key == "short-checkout"
    assert "'order_completed'" in out["query"] and "'short-checkout'" in out["query"]
    set_fake_handler(None)


def test_if_the_ai_is_busy_the_template_is_used():
    out = design.build(ISSUE)  # fake provider with no handler: the AI fails
    assert out["words_source"] == "template" and out["plan"].per_variant == 49777


def test_posthog_query_cannot_be_broken_by_odd_names():
    q = posthog.query("x'; DROP TABLE events; --", "a b'c", "ok_event")
    assert "DROP TABLE" not in q.replace("DROPTABLEevents", "") and "';" not in q
    assert "argMin(properties.$feature_flag_response" in q and "variants_seen = 1" in q


# --- Linear ---------------------------------------------------------------------------------------

def signed(body: dict, secret: str = "whsec_test") -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    return raw, {"linear-signature": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
                 "linear-event": "AgentSessionEvent", "content-type": "application/json"}


def event(action: str, **extra) -> dict:
    return {"type": "AgentSessionEvent", "action": action, "webhookTimestamp": int(time.time() * 1000),
            "agentSession": {"id": "sess-1", "issue": {"title": "Test shorter checkout"}}, **extra}


def test_signature_checks():
    raw, h = signed(event("created"))
    assert linear.verify(raw, h["linear-signature"])[0]
    assert not linear.verify(raw, "0" * 64)[0] and not linear.verify(raw, None)[0]
    stale = signed({**event("created"), "webhookTimestamp": int(time.time() * 1000) - 120_000})
    assert linear.verify(*stale[:1], stale[1]["linear-signature"])[1].startswith("stale")


def test_unsigned_webhooks_are_rejected(client, linear_api):
    raw, h = signed(event("created"), secret="wrong")
    assert client.post("/webhooks/linear", content=raw, headers=h).status_code == 401 and linear_api == []


def test_a_mention_gets_a_thought_first_then_the_plan(client, linear_api):
    raw, h = signed(event("created", promptContext=ISSUE))
    assert client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "d1"}).json() == {"ok": True}
    acts = contents(linear_api)
    assert acts[0]["type"] == "thought"  # acknowledges within 10 seconds
    assert [a["type"] for a in acts[1:]] == ["action", "action", "response"]
    assert "49,777 users per variant" in acts[2]["result"] and "## Experiment plan" in acts[-1]["body"]


def test_duplicate_deliveries_are_answered_once(client, linear_api):
    raw, h = signed(event("created", promptContext=ISSUE))
    client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "same"})
    assert client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "same"}).json()["duplicate"] is True
    assert sum(a["type"] == "response" for a in contents(linear_api)) == 1


def test_a_reply_recalculates(client, linear_api):
    raw, h = signed(event("created", promptContext=ISSUE))
    client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "d1"})
    raw, h = signed(event("prompted", agentActivity={"id": "a2", "content": {"type": "prompt", "body": "baseline is 6%, detect 20%"}}))
    client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "d2"})
    final = contents(linear_api)[-1]
    assert final["type"] == "response" and "| Baseline rate | 6% |" in final["body"]


def test_a_reply_after_a_restart_fetches_the_issue(client, linear_api):
    raw, h = signed(event("prompted", agentSession={"id": "sess-9"}, agentActivity={"id": "a", "content": {"body": "detect a 20% lift"}}))
    client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "d3"})
    assert any("agentSession(id" in q for q, _ in linear_api) and "| Baseline rate | 3.2% |" in contents(linear_api)[-1]["body"]


def test_stop_signal_stops(client, linear_api):
    raw, h = signed(event("prompted", agentActivity={"id": "a", "signal": "stop", "content": {"body": ""}}))
    client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "d4"})
    assert contents(linear_api) == [{"type": "response", "body": "Stopped."}]


def test_failures_are_reported_in_linear(client, linear_api, monkeypatch):
    monkeypatch.setattr(design, "build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    raw, h = signed(event("created", promptContext=ISSUE))
    client.post("/webhooks/linear", content=raw, headers={**h, "linear-delivery": "d5"})
    assert contents(linear_api)[-1]["type"] == "error" and "boom" in contents(linear_api)[-1]["body"]


def test_other_webhook_types_are_ignored(client, linear_api):
    raw, h = signed({"type": "Issue", "action": "create", "webhookTimestamp": int(time.time() * 1000)})
    assert client.post("/webhooks/linear", content=raw, headers={**h, "linear-event": "Issue"}).json()["ignored"] == "Issue"


def test_install_asks_for_an_app_install_that_can_be_mentioned(client):
    r = client.get("/install", follow_redirects=False)
    loc = r.headers["location"]
    assert r.status_code == 307 and loc.startswith("https://linear.app/oauth/authorize?")
    assert "actor=app" in loc and "app%3Amentionable" in loc and "app%3Aassignable" in loc and "client_id=cid" in loc


def test_callback_rejects_a_forged_state(client):
    assert client.get("/oauth/callback?code=abc&state=123.fake").status_code == 400


def test_try_it_endpoint(client):
    d = client.post("/api/design", json={"text": "Test shorter checkout. Converts at 3.2%, 2,000 visitors a day, detect a 10% lift.",
                                         "use_ai": False}).json()
    assert d["plan"]["per_variant"] == 49777 and d["plan"]["days_rounded"] == 56


def test_status_shows_the_urls_to_paste_into_linear(client):
    s = client.get("/api/status").json()
    assert s["callback_url"].endswith("/oauth/callback") and s["webhook_url"].endswith("/webhooks/linear")
    assert s["configured"] == {"client_id": True, "client_secret": True, "webhook_secret": True}


def test_lift_with_the_number_first():
    from expagent import design
    assert design.numbers("what if we only care about a 10% lift?")["mde"] == pytest.approx(0.10)
    assert design.numbers("a 15% relative improvement")["mde"] == pytest.approx(0.15)
    assert design.numbers("baseline 12.5%, a 2 pp absolute lift")["mde"] == pytest.approx(0.16)


def test_a_follow_up_lift_overrides_the_issue():
    from expagent import design
    out = design.build("Checkout converts at 12.5%. We care about a 15% relative lift. 1,600 people a week.",
                       "what if we only care about a 10% lift?", use_ai=False)
    assert out["plan"].mde_relative == pytest.approx(0.10)
