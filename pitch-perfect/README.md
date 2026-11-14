# Pitch Perfect

Upload a startup pitch deck (PDF or PowerPoint). Get an investor's section-by-section review, a numbers check, and practice the questions investors will ask.

**Live:** https://pitch-perfect-j6rj.onrender.com

## What it does

1. **Reads the deck.** PDF pages or PowerPoint slides (including speaker notes and tables) become plain text, one entry per slide (`pitch/deck.py`). Image-only decks get a clear message instead of an empty review.
2. **Checks the numbers in code** (`pitch/numbers.py`), because arithmetic shouldn't be left to an AI:
   - the same metric stated differently on different slides (e.g. MRR $40K on slide 4, $35K on slide 9)
   - market sizes out of order (TAM ≥ SAM ≥ SOM), or only a TAM
   - use-of-funds percentages that don't add up to 100%
   - no funding ask anywhere
   - stated runway that doesn't match raise ÷ burn
3. **Reviews ten sections** an investor looks for: problem, solution, why now, market, traction, business model, competition, team, financials, the ask. Each gets a 0–5 score, one line of feedback, one fix, and a quote from the slides. Quotes are checked against the deck and flagged if they aren't there. The overall score is computed in code from the section scores, so it means the same thing every time. Reviews are cached per deck.
4. **Investor practice.** The AI plays a sceptical investor who has read the deck and asks one question at a time, steering toward the weakest sections and toward topics you've answered badly. Each answer is scored 1–5 with what worked, what's missing, and a stronger answer that uses only facts from the deck or your answer; missing facts appear as `[placeholders]`.

## Privacy

Decks aren't saved. The slide text is sent to the AI provider (Groq, then Google as backup) to produce the review. The page keeps your deck and practice history in the browser tab only.

## Tests

`pytest -q` from the repo root. Pitch Perfect's tests build real PDF and PowerPoint files in memory, check every numbers rule on a sample deck with planted mistakes, and fake the AI to test section completion, quote checking, caching, question steering and grading.

## Run locally

```bash
pip install -r pitch-perfect/requirements.txt
PYTHONPATH=.:pitch-perfect uvicorn --app-dir pitch-perfect pitch.main:app --reload
```
