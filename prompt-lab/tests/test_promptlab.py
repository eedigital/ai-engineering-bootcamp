"""Prompt Lab: the starter tasks, the code checks, a run, the comparison, the AI improver and the API. The AI is faked."""

import json
import os

os.environ["LLM_PROVIDERS"] = "fake"
os.environ["LLM_RATE_LIMIT_WAIT_S"] = "0"

import pytest
from fastapi.testclient import TestClient

from llm import set_fake_handler
from promptlab import checks, compare, improve, main, runner
from promptlab.models import Case, Expect, Task
from promptlab.samples import SAMPLES, TITLES, TRIAGE

ANSWERS = {c.input: c.expect.fields for c in TRIAGE.cases}


def triage_model(messages):
    """Answers correctly only when the prompt spells out the keys, like a real model given a vague prompt."""
    system, user = messages[0]["content"], messages[-1]["content"]
    if "exactly two keys" in system:
        return json.dumps(ANSWERS[user])
    return json.dumps({"topic": "check-in", "urgent": "yes"})


@pytest.fixture
def client():
    main._hits.clear()
    yield TestClient(main.app)
    set_fake_handler(None)


# --- starter tasks --------------------------------------------------------------------------

@pytest.mark.parametrize("task", SAMPLES, ids=lambda t: t.id)
def test_each_starter_task_is_valid_with_held_out_and_injection_cases(task: Task):
    Task.model_validate(task.model_dump())  # what the page sends back must validate too
    ids = [c.id for c in task.cases]
    assert len(ids) == len(set(ids))
    assert sum(c.heldout for c in task.cases) >= 2
    assert any("instructions" in c.note for c in task.cases)
    assert len(task.versions) == 2


def test_triage_cases_only_use_the_categories_the_prompt_names():
    named = {"arrival", "maintenance", "complaint", "booking_change", "question", "other"}
    for c in TRIAGE.cases:
        assert c.expect.fields["category"] in named
        assert f'"{c.expect.fields["category"]}"' in TRIAGE.versions[1]


def test_title_cases_ask_for_the_neighbourhood_as_written():
    for c in TITLES.cases:
        assert c.expect.contains[0] in c.input
        assert c.expect.max_chars == 50


# --- code checks ----------------------------------------------------------------------------

TRIAGE_EXPECT = Expect(fields={"category": "arrival", "urgent": False})


def test_json_answer_passes_and_strings_ignore_case_and_fences():
    assert checks.score('{"category": "arrival", "urgent": false}', TRIAGE_EXPECT).passed
    assert checks.score('```json\n{"category": "Arrival", "urgent": false}\n```', TRIAGE_EXPECT).passed


def test_json_answer_fails_with_a_reason_per_problem():
    s = checks.score('{"category": "arrival", "urgent": "false", "tone": "calm"}', TRIAGE_EXPECT)
    assert not s.passed
    assert s.reasons == ['urgent: expected false, got "false"', "Extra keys: tone"]
    assert checks.score("arrival, not urgent", TRIAGE_EXPECT).reasons == ["Not a valid JSON object"]
    assert checks.score("[1, 2]", TRIAGE_EXPECT).reasons == ["Not a valid JSON object"]
    assert checks.score('{"urgent": false}', TRIAGE_EXPECT).reasons == ['Missing "category"']


def test_numbers_and_bools_are_not_mixed_up():
    assert not checks.score('{"n": 1}', Expect(fields={"n": True})).passed
    assert checks.score('{"n": 2.0}', Expect(fields={"n": 2})).passed


def test_text_checks_keep_accents_and_count_characters():
    e = Expect(max_chars=50, contains=["Gràcia"], not_contains=["!"])
    assert checks.score("Rooftop terrace flat in Gràcia", e).passed
    assert checks.score("Rooftop terrace flat in Gracia", e).reasons == ['Missing "Gràcia"']
    s = checks.score("AMAZING ROOFTOP TERRACE FLAT IN THE HEART OF GRÀCIA!!!", e)
    assert s.reasons == ["54 characters, limit 50", 'Contains "!"']
    assert checks.score("  Yes  ", Expect(equals="yes")).passed


def test_describe_reads_like_a_sentence():
    assert checks.describe(TRIAGE_EXPECT) == 'JSON category = "arrival", urgent = false'
    assert checks.describe(Expect(max_chars=50, contains=["Alfama"])) == 'at most 50 characters; includes "Alfama"'


# --- a run ----------------------------------------------------------------------------------

def test_the_designed_prompt_beats_the_vague_one():
    set_fake_handler(triage_model)
    v1 = [runner.run_case(TRIAGE.versions[0], c, "json", "fake") for c in TRIAGE.cases]
    v2 = [runner.run_case(TRIAGE.versions[1], c, "json", "fake") for c in TRIAGE.cases]
    assert not any(r["passed"] for r in v1)
    assert all(r["passed"] for r in v2)
    assert v1[0]["reasons"] == ['Missing "category"', 'urgent: expected false, got "yes"', "Extra keys: topic"]
    assert v2[0]["tokens_estimated"] and v2[0]["input_tokens"] > v1[0]["input_tokens"]  # a longer prompt costs more


def test_a_provider_without_a_key_is_an_error_not_a_fail(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = runner.run_case("Say hi", TRIAGE.cases[0], "json", "groq")
    assert r["passed"] is None and "GROQ_API_KEY" in r["error"]


def test_only_providers_with_keys_are_offered(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "claude,groq,gemini")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert [p["name"] for p in runner.providers()] == ["groq"]


# --- comparison -----------------------------------------------------------------------------

def R(version, case, passed, heldout=False, ms=100, tin=100, tout=10):
    return compare.Result(version=version, case_id=case, heldout=heldout, passed=passed,
                          latency_ms=ms, input_tokens=tin, output_tokens=tout)


def test_quality_wins_first_and_rates_split_open_and_held_out():
    s = compare.summarise([R(1, "a", True), R(1, "b", False), R(1, "c", False, heldout=True),
                           R(2, "a", True), R(2, "b", True), R(2, "c", True, heldout=True)])
    v1, v2 = s["versions"]
    assert (v1["pass_rate"], v1["open_pass_rate"], v1["heldout_pass_rate"]) == (pytest.approx(1 / 3), 0.5, 0.0)
    assert s["winner"] == 2
    assert s["why"].startswith("V2 passed 3 of 3 cases (100%). V1 passed 1 (33%).")


def test_a_tie_on_quality_goes_to_the_cheaper_version_and_says_so():
    s = compare.summarise([R(1, "a", True, tin=400), R(2, "a", True, tin=100)], compare.Prices(input=1.0, output=4.0))
    assert s["winner"] == 2
    assert s["versions"][1]["cost_per_1000"] == pytest.approx((100 * 1.0 + 10 * 4.0) / 1000)
    assert "ties with V1 on quality, and costs less per call" in s["why"]


def test_a_version_that_only_fits_the_open_cases_is_flagged():
    rs = [R(1, f"o{i}", True) for i in range(4)] + [R(1, "h1", False, True), R(1, "h2", False, True), R(1, "h3", True, True)]
    s = compare.summarise(rs)
    assert s["versions"][0]["overfit"] is True
    assert "may be fitted to the test" in s["why"]


def test_failed_calls_are_left_out_of_the_score():
    s = compare.summarise([R(1, "a", True), R(1, "b", None)])
    assert s["versions"][0]["errors"] == 1 and s["versions"][0]["pass_rate"] == 1.0
    assert "Some calls failed" in s["why"]
    assert compare.summarise([R(1, "a", None)])["winner"] is None


# --- the AI improver ------------------------------------------------------------------------

def F(case: Case, heldout=False, answer='{"topic": "check-in"}'):
    return improve.Failure(case_id=case.id, input=case.input, expected=checks.describe(case.expect),
                           answer=answer, reasons=['Missing "category"'], heldout=heldout)


SUGGESTION = {"diagnosis": ["The prompt never names the keys."], "changes": ["Listed the two keys and the categories."],
              "prompt": "Return a JSON object with exactly two keys: category and urgent. Categories: arrival, maintenance."}


def test_held_out_failures_never_reach_the_ai():
    seen = []
    set_fake_handler(lambda m: (seen.append(m[-1]["content"]), json.dumps(SUGGESTION))[1])
    out = improve.suggest("Sort guest messages", "json", TRIAGE.versions[0],
                          [F(TRIAGE.cases[0]), F(TRIAGE.cases[8], heldout=True)], passing=0)
    assert out["withheld"] == 1 and out["copied"] == []
    assert TRIAGE.cases[0].input in seen[0] and TRIAGE.cases[8].input not in seen[0]
    assert out["suggestion"]["prompt"] == SUGGESTION["prompt"]


def test_a_rewrite_that_copies_a_test_input_is_flagged():
    leaky = dict(SUGGESTION, prompt=SUGGESTION["prompt"] + " If they say the door code you sent isn't working and "
                 "we're standing outside, it is arrival and urgent.")
    set_fake_handler(lambda m: json.dumps(leaky))
    out = improve.suggest("Sort guest messages", "json", TRIAGE.versions[0], [F(TRIAGE.cases[1])], passing=0)
    assert out["copied"] == ["locked-out"]


def test_nothing_to_learn_from_when_only_held_out_cases_fail():
    with pytest.raises(ValueError):
        improve.suggest("t", "json", "p", [F(TRIAGE.cases[8], heldout=True)], passing=3)


# --- API ------------------------------------------------------------------------------------

def test_page_health_samples_and_providers(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").json() == {"status": "ok", "providers": ["fake"]}
    tasks = client.get("/api/samples").json()["tasks"]
    assert [t["id"] for t in tasks] == ["guest-messages", "listing-titles"]
    assert client.get("/api/providers").json()["providers"] == [{"name": "fake", "model": "fake"}]


def test_run_scores_one_case(client):
    set_fake_handler(triage_model)
    body = {"prompt": TRIAGE.versions[1], "case": TRIAGE.cases[2].model_dump(), "output": "json", "provider": "fake"}
    r = client.post("/api/run", json=body).json()
    assert r["passed"] is True and r["case_id"] == "ceiling-leak" and r["latency_ms"] >= 0


def test_run_refuses_a_provider_this_server_does_not_offer(client):
    body = {"prompt": "p", "case": TRIAGE.cases[0].model_dump(), "output": "json", "provider": "claude"}
    r = client.post("/api/run", json=body)
    assert r.status_code == 422 and "isn't available here" in r.json()["error"]


def test_run_rejects_a_malformed_case(client):
    case = TRIAGE.cases[0].model_dump() | {"expect": {"fields": {"category": "arrival"}, "sounds_good": True}}
    assert client.post("/api/run", json={"prompt": "p", "case": case, "output": "json"}).status_code == 422


def test_compare_and_improve_over_http(client):
    s = client.post("/api/compare", json={"results": [R(1, "a", False).model_dump(), R(2, "a", True).model_dump()]}).json()
    assert s["winner"] == 2
    set_fake_handler(lambda m: json.dumps(SUGGESTION))
    body = {"task": "Sort guest messages", "output": "json", "prompt": TRIAGE.versions[0],
            "failures": [F(TRIAGE.cases[0]).model_dump()], "passing": 0}
    assert client.post("/api/improve", json=body).json()["suggestion"]["changes"] == SUGGESTION["changes"]


def test_improve_reports_a_busy_or_broken_ai_kindly(client):
    set_fake_handler(lambda m: "not json at all")
    body = {"task": "t", "output": "json", "prompt": "p", "failures": [F(TRIAGE.cases[0]).model_dump()]}
    r = client.post("/api/improve", json=body)
    assert r.status_code == 502 and "Try again" in r.json()["error"]


def test_rate_limit_per_visitor(client, monkeypatch):
    monkeypatch.setattr(main, "PER_IP", 2)
    set_fake_handler(triage_model)
    body = {"prompt": TRIAGE.versions[1], "case": TRIAGE.cases[0].model_dump(), "output": "json", "provider": "fake"}
    codes = [client.post("/api/run", json=body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
