# Grant Finder

Describe your organization once. Grant Finder searches open US federal grants on Grants.gov, checks each one's eligibility rules against yours, quotes the grant to show why, ranks the matches, and drafts the core of an application.

**Live:** https://grant-finder.onrender.com ← confirm once deployed

## How it works

```
Your profile ──► AI picks 2–3 search terms ──► Grants.gov search (open grants only)
                                                      │
                     for each grant, two at a time:   ▼
             Grants.gov details ──► code rules ──► AI assessment ──► quote check
                                      │                                  │
                         not eligible: stop here          flags any quote not in the grant
                         (no AI call, can't be wrong)
```

1. **Search.** The AI turns your project into a few search terms, or you type your own. Grants.gov returns open opportunities, narrowed to your applicant type.
2. **Rules in code first.** Whether your organization type is listed, whether the deadline has passed and whether you're asking for more than the largest award are checked in plain Python (`grants/rules.py`). If code says you're not eligible, the AI is never asked.
3. **AI for the fuzzy parts.** The AI lists the grant's real requirements, marks each met, not met or unknown, and must copy the grant's exact words as evidence. Its answer is validated against a fixed format (`grants/schemas.py`) with one repair attempt, as in Week 1.
4. **Quote check.** Every quote the AI gives is searched for in the grant text (`ground()` in `grants/ai.py`). Quotes that aren't there are flagged in red on the page. The AI can't mark its own homework.
5. **Code beats the AI.** If the rules say ineligible, an optimistic AI verdict is overruled.
6. **Draft.** For any match, the AI writes a project summary, statement of need, fit with the grant, and budget outline, using only your facts. Missing facts become highlighted `[placeholders]`, listed under "Check or fill in before submitting".

Grant text comes from a third party, so it's wrapped in `<grant>` tags and the model is told to treat it as data, never instructions.

## What's tested (no network needed)

`pytest -q` from the repo root runs both apps' tests. Grant Finder's cover: parsing Grants.gov's money and date formats, the eligibility rules (including "for profit organizations other than small businesses" not matching small businesses), retrying a search without the eligibility filter when it returns nothing, the quote check, code overruling the AI, the AI never being called for ineligible grants, and clean errors when the AI fails.

## Known limits

- **Federal grants only.** State, city and private foundation grants aren't on Grants.gov.
- **Free AI limits.** Each search checks up to 10 grants, two at a time, to stay inside free-tier limits. The page retries a grant automatically if the AI is busy.
- **Grants.gov field names** aren't fully documented. `grants/grantsgov.py` reads them defensively; if Grants.gov changes a field, fix `normalize()` and `tests/fixtures/fetch_opportunity.json`.
- **Not legal or financial advice.** Always read the full notice before applying.

## Run locally

```bash
pip install -r grants-finder/requirements.txt
PYTHONPATH=.:grants-finder uvicorn --app-dir grants-finder grants.main:app --reload
```

This product uses the Grants.gov API but is not endorsed or certified by the U.S. Department of Health and Human Services.
