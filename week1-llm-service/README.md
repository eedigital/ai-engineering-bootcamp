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

Run `python week1-llm-service/scripts/bench.py --url <your-url> --n 50` and paste the table it prints here.

| Metric | Value |
| --- | --- |
| Calls | |
| Success rate | |
| Validation failures (502) | |
| Needed a repair re-prompt | |
| Median latency | |
| p90 latency | |

**What broke and what I changed:** _(fill this in: the most useful part of the README)_
