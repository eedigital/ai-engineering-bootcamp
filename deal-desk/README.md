# Deal Desk

**Get one export deal right.** A concept prototype built to plug into [ICC One Click](https://oneclick.iccwbo.org/). Not an official ICC product.

**Live:** https://deal-desk-gzud.onrender.com · **Integration guide:** `/integrate` · **API reference:** `/docs`

## One click

The home page works like accounting software for exporting: the rules are public, but people pay not to make mistakes.

1. **Drop in what you have.** Paste the buyer's email or order, attach their PDF, or describe the deal in one sentence.
2. **It finds and works out the rest.** Product and its HS code from **all 5,612 six-digit codes of HS 2022** (`dealdesk/hs.py`, public-domain data from UN Comtrade). A hand-made list (`dealdesk/products.py`) covers common exports in plain words ("green coffee" is 090111, not roasted); anything else is matched by searching the full list, with alternatives to pick from, and the AI's guesses are used only if they're real codes. You can search all codes on the check screen (`GET /api/hs?q=`). Then quantities, price, unit price, route and ports, containers, bags, what the buyer asked for, and the risky terms. Every field shows where it came from: from the message, worked out, assumed, or your saved details.
3. **At most three questions,** in plain words, only for what it can't find ("Green or roasted?", "Who books the transport?"). Anything else is assumed, safely, and marked.
4. **One set of figures, three documents:** a quotation, proforma invoice and packing list, printable or saved as PDF, with gaps highlighted and fillable in place.
5. **Checks before sending:** totals that don't add up, overloaded containers, part-full packages, FOB asked for container cargo, credit for a new buyer, letters of credit with FCA, insurance at 110% for CIF/CIP, the EU Deforestation Regulation, organic certificates in TRACES, trade-agreement proof of origin.

**Your products and the expert check.** Once a product's HS code is confirmed (by the buyer's order, by you, or by an expert), it's saved to your product list and used on every later deal without asking. If you're not sure, **Ask an expert** works inside the deal: the request carries what the deal already knows, the deal shows "With an expert", and the answer updates the code on all three documents. The expert is a labelled demo for now (`dealdesk/expert.py`, `EXPERT_PRICE`, `EXPERT_DEMO_DELAY_S`); in production the request would go to an expert view used by ICC's network, a chamber or a broker.

**The paywall.** The reading, the checks, the advice and the list of documents to prepare are free. The quotation, proforma invoice and packing list unlock with a **deal pass**: one product to one market (coffee to Germany, say), for 90 days, with unlimited edits. A bank, chamber or export agency can pay instead by giving its businesses a code, which is One Click's sponsored "Export Ready" route. Documents are locked on the server, not just blurred: without a valid pass, `/api/pack` returns no documents. A pass is a signed token (`dealdesk/paywall.py`), so no database is needed. The checkout is a demo and charges nothing; in production a payment provider such as Stripe would issue the pass after payment. Settings: `PAYWALL` (on/off), `DEAL_PASS_PRICE`, `DEAL_PASS_CURRENCY`, `DEAL_PASS_DAYS`, `SPONSOR_CODES` (`CODE:Sponsor name,...`; demo codes `CHAMBER-DEMO` and `BANK-DEMO`), `PAYWALL_SECRET`.

It works even when the AI is busy: a plain-code reader (`dealdesk/extract.py`) fills in most of the deal, and the AI only adds what needs judgement. The reader tells the quantity apart from package sizes ("60 kg bags", "sacos de 70 kg"), prices per kg and weights per container, and handles totals, "640 x 60 kg", tonnes, European decimals and gross versus net weight. Company details and saved deals stay in the browser. The original step-by-step planner is at `/wizard`.

## What the advice covers

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
| AI assistant | **Tool definitions** at `GET /api/tools` for `deal_desk_plan`, `deal_desk_pack` and `deal_desk_read` |
| The chat itself | **Launch link:** `/?text=<the SME's message>` opens Deal Desk with the deal already read |
| SME Trade Catalogue | **Launch link:** `/?product=…&origin=…&destination=…&value=…&currency=…&mode=…&buyer=…` |
| Chambers | Certificate-of-origin handoff in every deal pack |

The embed only exchanges messages with the page that embedded it. For production: pass One Click's signed-in user via a short-lived signed token, restrict `ALLOWED_ORIGINS` to One Click's domains, translate the interface (One Click runs in English, Arabic, French and Spanish), link each rule to ICC's official text, and route expert reviews to chambers.

## Tests

`pytest -q` from the repo root. 40 tests for the planner and 115 for one click and the paywall (product lookup, the plain-code reader, quantities however the buyer writes them, what's asked and assumed, one set of figures across documents, HS search across everyday products, each check, and that documents stay locked without a genuine, unexpired pass for that product and market). Planner tests cover every Incoterms® choice, that sea-only rules are never recommended for containers or air, payment choices and warnings, documents by deal, placeholder-only terms, the AI reader's quote check and prompt-injection wrapping, the tools endpoint, the embed script and CORS.

## Run locally

```bash
pip install -r deal-desk/requirements.txt
PYTHONPATH=.:deal-desk uvicorn --app-dir deal-desk dealdesk.main:app --reload
```
