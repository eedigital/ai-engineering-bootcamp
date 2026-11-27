# Prompt Lab

Write prompt versions, run them on real test cases, and ship the one that wins on quality, cost and speed. Held-out cases show whether a better score is real or just fitted to the test.

**Live:** https://prompt-lab-osyn.onrender.com

## What it does

1. **Starts from a real task.** Two starter tasks from vacation rentals, each with a vague first prompt and a designed second one:
   - **Guest messages:** sort a guest's message into one of 6 categories and flag the urgent ones (12 cases, 4 held out).
   - **Listing titles:** write a title of 50 characters or fewer that names the neighbourhood exactly as written (7 cases, 3 held out).

   Both include messages that try to give the model instructions, so prompt injection is part of the test. You can edit the cases as JSON or bring your own.
2. **Runs every version on every case**, one call at a time, so the grid fills in live. Each version can use a different model, which makes it a model comparison too. Every call records the answer, time and tokens.
3. **Scores in code** (`promptlab/checks.py`). A case passes only if every rule holds: exact JSON keys and values, a character limit, words it must or must never contain. Each fail comes with a reason a person can read ("urgent: expected false, got "yes""). The model never grades itself.
4. **Compares the versions** (`promptlab/compare.py`): pass rate on open and held-out cases, average time, tokens per call, and the cost of 1,000 calls at the prices you enter. It picks a winner by quality first, then cost, then speed, and says why. A version that does much better on open cases than held-out ones is flagged as probably fitted to the test.
5. **Improves a version with AI** (`promptlab/improve.py`). The AI sees the prompt and its failing open cases, then returns what went wrong, what it changed and a rewritten prompt. Held-out cases never reach it, so they stay a fair test. If the rewrite copies text from a test input, it's flagged: that would pass the case without making the prompt better.

## Design choices

- **Code checks before AI judges.** Exact rules are cheaper, repeatable and explainable. An AI judge would add its own errors to the score you're trying to trust.
- **Held-out cases.** Tuning a prompt on its own test cases overfits like tuning a model on its test set. The improver only learns from open cases; held-out cases measure the result.
- **Tokens are cost.** The page shows each prompt's size because it's paid on every call. A shorter prompt that passes the same cases wins the tie.
- **Free tiers only on the live site.** Visitors run prompts on Groq and Gemini free tiers. Claude works locally, or on the live site once a spending cap is set.

## Tests

`pytest -q` from the repo root. Prompt Lab's tests check the starter tasks, every scoring rule, a full run where the designed prompt beats the vague one, the comparison maths and verdicts, that held-out failures never reach the improver, the copy check, and the API with its rate limit. The AI is faked.

## Run locally

```bash
pip install -r prompt-lab/requirements.txt
PYTHONPATH=.:prompt-lab uvicorn --app-dir prompt-lab promptlab.main:app --reload
```

Set `LLM_PROVIDERS` and at least one key in `.env` (see `.env.example`). Add `claude` to `LLM_PROVIDERS` with `ANTHROPIC_API_KEY` set to compare Claude too.
