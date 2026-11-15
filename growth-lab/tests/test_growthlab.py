"""Growth Lab: invented data, funnel maths, roadmap sizing and scheduling, readout decisions, the exec readout's
number check, the launch quote and the API."""

import json
import os

os.environ["LLM_PROVIDERS"] = "fake"
os.environ["LLM_RATE_LIMIT_WAIT_S"] = "0"
os.environ.pop("LINEAR_API_KEY", None)
os.environ.pop("POSTHOG_KEY", None)

import pytest
from fastapi.testclient import TestClient

from growthlab import exec_readout, funnel, launch, linear, main, posthog, readouts, roadmap, stats
from llm import set_fake_handler


@pytest.fixture
def client():
    main._hits.clear()
    main._readout_cache.update(at=0.0, value=None)
    yield TestClient(main.app)
    set_fake_handler(None)


# --- data and funnel ---------------------------------------------------------------------

def test_the_invented_data_is_the_same_every_run():
    a = funnel.summary()["totals"]
    funnel.rows.cache_clear() if hasattr(funnel.rows, "cache_clear") else None
    from growthlab import data
    data.rows.cache_clear()
    assert funnel.summary()["totals"] == a


def test_funnel_steps_only_shrink_and_rates_add_up():
    s = funnel.summary()
    counts = [x["count"] for x in s["steps"]]
    assert counts == sorted(counts, reverse=True)
    t = s["totals"]
    assert s["cvr"] == pytest.approx(s["cvr_direct"] + s["cvr_rep"]) and t["paid"] == t["paid_direct"] + t["paid_rep"]


def test_the_biggest_leak_is_pricing_to_checkout():
    leak = funnel.biggest_leak()
    assert (leak["from"], leak["to"]) == ("Saw pricing", "Started checkout") and 0.15 < leak["rate"] < 0.20


def test_breakdowns_sum_to_the_total():
    total = funnel.summary()["totals"]["paid"]
    assert sum(p["paid"] for p in funnel.by("product")) == total == sum(c["paid"] for c in funnel.by("channel"))


# --- stats -------------------------------------------------------------------------------

def test_readout_maths_matches_known_values():
    r = stats.compare(10_000, 500, 10_000, 560)
    assert r.p_value == pytest.approx(0.058, abs=0.002) and r.ci_low < 0 < r.ci_high and r.srm_p == pytest.approx(1.0)


def test_sample_ratio_mismatch_is_detected():
    assert stats.compare(10_000, 500, 10_500, 520).srm_p < 0.01


# --- roadmap -----------------------------------------------------------------------------

def test_six_to_ten_tests_fit_in_ninety_days_and_one_is_a_launch():
    planned = [t for t in roadmap.plan() if t.start_week]
    assert 6 <= len(planned) <= 10 and any(t.kind == "launch" for t in planned)
    assert all(t.start_week + t.sized["weeks"] - 1 <= roadmap.HORIZON_WEEKS for t in planned)


def test_tests_on_the_same_surface_never_overlap():
    planned = [t for t in roadmap.plan() if t.start_week]
    for a in planned:
        for b in planned:
            if a is b or a.surface != b.surface:
                continue
            if a.product and b.product and a.product != b.product:
                continue
            a_end, b_end = a.start_week + a.sized["weeks"], b.start_week + b.sized["weeks"]
            assert a_end <= b.start_week or b_end <= a.start_week, (a.id, b.id)


def test_sizing_uses_the_power_formula_and_surface_traffic():
    t = next(x for x in roadmap.plan() if x.id == "T1")
    assert t.sized["per_variant"] == stats.per_variant(t.sized["baseline"], 0.10)
    assert t.sized["weeks"] * t.sized["weekly_users"] >= 2 * t.sized["per_variant"]


def test_deferred_tests_say_why():
    deferred = [t for t in roadmap.plan() if not t.start_week]
    assert deferred and all(t.defer_reason for t in deferred)
    assert any("weeks of traffic" in t.defer_reason for t in deferred) and any("taken by higher-priority" in t.defer_reason for t in deferred)


def test_every_test_has_a_linear_issue_and_a_flag():
    for t in roadmap.plan():
        d = roadmap.as_dict(t)
        assert d["linear"]["url"].startswith("https://linear.app/") and t.flag and "/" not in t.flag


# --- readouts ----------------------------------------------------------------------------

def test_the_three_simulated_readouts_get_the_intended_verdicts():
    verdicts = {r["test_id"]: r["verdict"] for r in readouts.all_readouts()}
    assert verdicts == {"T3": "Ship", "T8": "Inconclusive", "T7": "Don't ship as is"}


def test_inconclusive_says_what_the_interval_rules_out():
    r = next(x for x in readouts.all_readouts() if x["test_id"] == "T8")
    assert r["primary"]["ci_low"] < 0 < r["primary"]["ci_high"] and "Keep control" in r["why"]


def test_a_mismatched_split_is_invalid():
    bad = readouts.Result("TX", "Broken split", "W1", readouts.Metric("m", 10_000, 1_000, 11_000, 1_200))
    assert readouts.judge(bad)["verdict"] == "Invalid"


def test_a_significant_drop_is_dont_ship():
    worse = readouts.Result("TY", "Worse", "W1", readouts.Metric("m", 10_000, 1_200, 10_000, 1_000))
    assert readouts.judge(worse)["verdict"] == "Don't ship"


def test_every_readout_has_a_finding():
    assert {f["test_id"] for f in readouts.findings()} == {r["test_id"] for r in readouts.all_readouts()}


# --- exec readout ------------------------------------------------------------------------

def test_template_readout_uses_only_facts():
    out = exec_readout.write(use_ai=False)
    assert out["source"] == "template" and exec_readout.unsupported_numbers(out["markdown"], out["facts"]) == []
    assert "Week 5 of 13" in out["markdown"] and "Decision needed" in out["markdown"]


def test_ai_readout_is_shown_when_its_numbers_check_out():
    f = exec_readout.facts()
    set_fake_handler(lambda m: json.dumps({"headline": f"CVR is {f['cvr_pct']}% with {f['new_members']} new members.",
                                           "body": f"Biggest leak: {f['leak']} at {f['leak_rate_pct']}%. T8 was inconclusive.",
                                           "decision_needed": ""}))
    out = exec_readout.write()
    assert out["source"] == "fake" and "1.34%" in out["markdown"]


def test_ai_readout_with_an_invented_number_is_rejected():
    set_fake_handler(lambda m: json.dumps({"headline": "CVR jumped to 2.9% and revenue hit $9,999,999.", "body": "Great week.",
                                           "decision_needed": ""}))
    out = exec_readout.write()
    assert out["source"] == "template" and "isn't in the data" in out["note"].replace("aren't", "isn't")


def test_ai_unavailable_falls_back_to_the_template():
    set_fake_handler(None)
    assert exec_readout.write()["source"] == "template"


# --- launch, instrumentation, Linear ------------------------------------------------------

def test_quote_in_network_complete_care():
    q = launch.quote("Complete Care", "NY", True)
    assert q.in_network and q.lines[0]["low"] == 1800 and q.low == 1800 + 200 and q.high == 1800 + 200 + 350 and q.first_visit_days == 9


def test_quote_self_pay_and_one_off():
    assert launch.quote("Complete Care", "TX", True).lines[0]["low"] == 1800  # in-network with select plans nationwide
    assert launch.quote("Complete Care", "FL", False).lines[0]["low"] == 3300  # self-pay, Medicare or no insurance
    q = launch.quote("Longevity Labs", "CA", False)
    assert q.low == q.high == 350 and len(q.lines) == 1
    assert launch.quote("BYO Labs Review", "NY", True).low == 250  # self-pay only, insurance or not


def test_hogql_quotes_the_flag_property():
    assert "properties.`$feature/know-your-cost`" in posthog.KPI_QUERIES["Know your cost: pricing → checkout by variant"]


def test_posthog_snippet_only_with_a_key(monkeypatch):
    assert posthog.snippet() == ""
    monkeypatch.setenv("POSTHOG_KEY", "phc_test")
    s = posthog.snippet()
    assert '"phc_test"' in s and '"autocapture": false' in s


def test_linear_without_a_key_returns_copyable_text():
    t = roadmap.plan()[0]
    out = linear.create(t)
    assert out["created"] is False and "**Decision rule.**" in out["markdown"] and t.flag in out["markdown"]


# --- API -----------------------------------------------------------------------------------

def test_pages_and_api(client):
    assert "Growth Lab" in client.get("/").text
    page = client.get("/know-your-cost").text
    assert "Know your cost" in page and "<!--POSTHOG-->" not in page
    assert client.get("/api/overview").json()["leak"]["to"] == "Started checkout"
    assert len(client.get("/api/roadmap").json()["tests"]) == 8
    assert client.get("/api/readouts").json()["readouts"][1]["verdict"] == "Inconclusive"
    assert client.get("/api/quote?product=Complete%20Care&state=NY&insurance=true").json()["in_network"] is True
    assert client.get("/api/quote?product=Nope").status_code == 422
    assert client.get("/api/exec?ai=false").json()["source"] == "template"
    assert client.post("/api/linear/T1").json()["created"] is False and client.post("/api/linear/T99").status_code == 404
