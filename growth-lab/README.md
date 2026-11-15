# Growth Lab

The first 90 days of a growth product manager at a membership health company, built as a working prototype. The company is modelled on Parsley Health's public product: Complete Care at its public prices, plus two invented product lines. **All funnel data, members and test results are invented.** This isn't affiliated with Parsley Health.

## What it does

| Section | What it shows | How it's built |
| --- | --- | --- |
| Funnel | 12 weeks of sign-ups by product line and channel, direct and rep-assisted CVR, and the biggest leak | Seeded simulation (`data.py`), so the numbers are the same every run |
| Roadmap | 8 hypotheses sized with power maths on each page's real traffic, scheduled so tests on the same page never overlap; 6 fit in 13 weeks and the 2 that don't say why | `roadmap.py`, `stats.py` |
| Readouts | Three simulated readouts with a written decision rule: one ships, one wins but fails a guardrail, one is inconclusive. Each has a confidence interval and a split check | `readouts.py` |
| Exec readout | The weekly update for the SVP of Growth. Code computes the facts, the AI writes the update, and code rejects any draft with a number that isn't in the facts | `exec_readout.py` |
| Launch | **Know your cost**: the full first-year cost and earliest appointment before checkout. Spec, owner map and a prospect-facing page | `launch.py`, `static/know-your-cost.html` |
| Instrumentation | Event schema, feature flags and the HogQL queries behind the readouts | `posthog.py` |

The roadmap lives in Linear as the project "Growth Lab: 90-day CRO and launch roadmap", with one issue per test (EED-5 to EED-12), the launch spec and the findings library as project documents.

## Run it

```bash
pip install -r growth-lab/requirements.txt
PYTHONPATH=.:growth-lab uvicorn growthlab.main:app --reload
```

Optional settings: `ANTHROPIC_API_KEY` (Claude writes the exec readout; otherwise Groq, Gemini, then a template), `POSTHOG_KEY` (the prospect page sends events), `LINEAR_API_KEY` (the roadmap's Send button creates issues).

## Tests

`pytest growth-lab` covers the funnel maths, power sizing, scheduling without overlaps, the decision rule (including an invalid split), the number check on the AI's readout, the quote and the API.
