# Week 1: Job Post Extractor

A live LLM service: messy job-post text in, validated JSON out, with guardrails on both sides.

**Live:** https://week1-job-extractor.onrender.com/docs

```bash
curl -X POST https://week1-job-extractor.onrender.com/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "Acme is hiring a Senior Backend Engineer in London (hybrid). £90k-£110k. Python, PostgreSQL."}'
```

```json
{
  "ok": true,
  "data": {
    "title": "Senior Backend Engineer", "company": "Acme", "location": "London",
    "work_mode": "hybrid", "seniority": "senior",
    "salary_min": 90000, "salary_max": 110000, "currency": "GBP",
    "skills": ["Python", "PostgreSQL"]
  },
  "provider": "gemini", "latency_ms": 1240.5, "attempts": 1, "redactions": 0
}
```

## How a request flows

1. **Rate limit:** 20 requests/minute per IP, so one caller can't burn your free quota.
2. **Input guardrails** (`app/guardrails.py`): length limits, prompt-injection patterns, and email and phone redaction. Blocked input returns 422 and never reaches the model.
3. **Model call** (`llm/client.py`): JSON mode, retries with backoff, and fallback across providers (Gemini, then Groq, then Ollama).
4. **Output validation** (`app/schemas.py`): Pydantic checks types, enums, currency format and salary order. On failure the model gets one repair prompt showing its error.
5. **Safe fallback:** if it's still invalid, the service returns 502 with a plain error, never a half-valid object or a stack trace.

## Run it locally

```bash
# from the repo root
python -m venv .venv && source .venv/bin/activate
pip install -r week1-llm-service/requirements.txt pytest
cp .env.example .env          # add at least one free key
pytest -q                      # 32 tests, no key needed
PYTHONPATH=. uvicorn --app-dir week1-llm-service app.main:app --reload
# open http://localhost:8000/docs
```

## Deploy to Render (free)

1. Push this repo to GitHub (public).
2. In Render: **New > Blueprint**, then pick the repo. It reads `render.yaml`.
3. Paste your `GEMINI_API_KEY` and `GROQ_API_KEY` when asked.
4. Wait for `/health` to go green, then put the URL at the top of this README.

The free instance sleeps when idle, so the first request after a while takes longer.

## What I measured

The benchmark sends the 8 sample posts (twice each) to the live service and scores every field against a hand-written correct answer (`samples/expected.jsonl`). Where a post is genuinely ambiguous, it accepts more than one answer. It runs on GitHub Actions against Render (`.github/workflows/bench.yml`) and saves the results to [BENCHMARK.md](BENCHMARK.md).

| | First run | After fixes |
| --- | --- | --- |
| Field accuracy | 90% (121/134) | **100% (134/134)** |
| Posts with every field right | 10/16 | 16/16 |
| Success rate | 100% | 100% |
| Validation failures | 0% | 0% |
| Needed a repair re-prompt | 0% | 0% |
| Median latency | 625 ms | 522 ms |
| p90 latency | 693 ms | 573 ms |

**What the first run found, and the fixes:**
- **A bug in my own guardrail, not the AI.** The privacy filter treated "95.000 - 120.000 EUR" (European number format) as a phone number and blanked it out, so the model never saw the salary. Ranges with thousands separators are now kept, and a regression test covers it.
- **A gap in the prompt.** With no rule for skills, the model only listed skills marked "required", so "Java or C#" came back empty. The prompt now asks for every technology the post names.
- **An unmapped title.** "Staff Platform Engineer" came back as unknown seniority. Staff, Principal and Head of now count as lead.

**Why that 100% isn't the real score:** the fixes were made by looking at these same 8 posts, so they fit them. The honest test is posts the fixes never saw.

### Held-out tests: posts the fixes never saw

Each fix was checked on a fresh set written after the fix, so no set is scored on code tuned to it.

| Run | Dev (8) | Held-out (15) | Held-out 2 (10) | Held-out 3 (5) |
| --- | --- | --- | --- | --- |
| First run | 90% | | | |
| Fixes 1–3 (phone filter, skills, Staff) | 100% | **99%** | | |
| Fix 4 (salary checked against the post) | 100% | 100% | **96%** | |
| Fix 5 (salary limit for large currencies) | 100% | 100% | 100% | **100%** |

The bold number in each row is the honest one: a set nobody had seen when the code was last changed.

**What each fresh set found:**
- **Held-out:** "¥8,000,000–¥11,000,000" came back with a maximum of 10,000,000. Fix: after the model answers, plain code reads every salary range in the post (`app/grounding.py`). If one end of the model's range matches and the other doesn't, the other end is taken from the post. Nothing is invented, and the response says `salary_corrected: true`.
- **Held-out 2:** Korean won and Indonesian rupiah salaries came back blank. The schema capped salaries at 10 million, so correct answers failed validation and the retry gave up (20% of calls needed one). Fix: a cap of 100 billion. Held-out 3 (Vietnamese dong, Colombian and Nigerian currencies, won, rupiah) then scored 100% with no retries.

Two of the five problems were in my own code (the phone filter and the salary cap), not the AI. Prompt tuning alone would never have found them.

**Caveats:** I wrote all the posts and their answers myself, and some fields accept more than one answer where a post is genuinely ambiguous. Real job ads would be a tougher test.

Full results: [benchmarks/](benchmarks/) and the latest runs in `BENCHMARK*.md`.
