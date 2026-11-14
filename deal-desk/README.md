# Deal Desk

**Get one export deal right.** A concept prototype built to plug into [ICC One Click](https://oneclick.iccwbo.org/). Not an official ICC product.

**Live:** https://deal-desk.onrender.com ← confirm once deployed · **Integration guide:** `/integrate` · **API reference:** `/docs`

An SME describes one deal, or pastes the buyer's order or email, and gets a deal pack:

1. **Delivery terms:** the Incoterms® 2020 rule that fits, why, how to write it, and a visual of which stages each side pays for and exactly where risk passes to the buyer. Alternatives and warnings (FOB/CFR/CIF for containers, DDP import taxes, the early risk transfer under CPT/CIP, the on-board bill of lading option under FCA).
2. **Getting paid:** advance payment, letter of credit (confirmed for high-risk destinations), documentary collection or open account, chosen from the buyer relationship, destination risk and deal size, with the ICC rules that apply (UCP 600, URC 522) and fraud checks for new buyers.
3. **Documents:** a tickable checklist that follows the deal (transport document by mode, insurance certificate for CIF/CIP, everything a letter of credit lists), with the certificate of origin handed off to the chamber.
4. **Draft terms** to send the buyer, with placeholders for every fact the seller must supply.
5. **Red flags** in the buyer's text (changed bank details, pay-after-resale, rejection at will, foreign courts), each quoted and checked against the text.

## Why it's built this way

- **Advice comes from rules, not AI.** Items 1 to 4 are plain code (`dealdesk/rules.py`), so the same deal always gets the same answer, and `POST /api/plan` works instantly with no AI quota. Trade advice that hallucinates is worse than none.
- **AI only reads.** The one AI step turns a buyer's message into deal details and red flags. Every red flag must quote the text, and quotes are checked.
- **ICC's IP stays ICC's.** Rule summaries are our own plain-language descriptions. The terms sheet points to the ICC Model International Sale Contract rather than copying it. Incoterms® is a registered trademark of ICC.

## Integrating with One Click

One Click has no public API, so Deal Desk offers the four standard ways a platform adds a tool:

| One Click today | Deal Desk connects by |
| --- | --- |
| Trade Action Plan (shipping and payment steps) | **Embed:** `<script src="/embed.js" data-target="#deal-desk" data-destination="Germany">`; the deal pack comes back as a `dealdesk:complete` event to save to the plan |
| AI assistant | **Tool definitions** at `GET /api/tools` for `deal_desk_plan` and `deal_desk_read` |
| SME Trade Catalogue | **Launch link:** `/?product=…&origin=…&destination=…&value=…&currency=…&mode=…&buyer=…` |
| Chambers | Certificate-of-origin handoff in every deal pack |

The embed only exchanges messages with the page that embedded it. For production: pass One Click's signed-in user via a short-lived signed token, restrict `ALLOWED_ORIGINS` to One Click's domains, translate the interface (One Click runs in English, Arabic, French and Spanish), link each rule to ICC's official text, and route expert reviews to chambers.

## Tests

`pytest -q` from the repo root. 40 tests: every Incoterms® choice, that sea-only rules are never recommended for containers or air, payment choices and warnings, documents by deal, placeholder-only terms, the AI reader's quote check and prompt-injection wrapping, the tools endpoint, the embed script and CORS.

## Run locally

```bash
pip install -r deal-desk/requirements.txt
PYTHONPATH=.:deal-desk uvicorn --app-dir deal-desk dealdesk.main:app --reload
```
