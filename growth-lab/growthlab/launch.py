"""The launch: "Know your cost". A pricing-page step that shows a prospect their whole first-year cost and how soon
they can be seen, before checkout.

Why: the biggest leak is pricing → checkout, and reviews cite surprise costs (membership, then visits billed to
insurance, then specialty labs) and long waits. The calculator makes the total and the wait visible up front.

Membership and product prices follow Parsley's public pricing (checked 15 Nov 2026): Complete Care $150/month in-network,
$275/month self-pay, 12-month commitment; Longevity Labs from $350/year; BYO Labs Review $250 one-time. Visit copays,
lab costs and waits are ILLUSTRATIVE and would come from RevOps, billing and scheduling data in production.
"""

from __future__ import annotations

from dataclasses import dataclass

MEMBERSHIP = {"Complete Care": {"in_network": 150 * 12, "self_pay": 275 * 12}}  # paid monthly; public pricing
ANNUAL_UPFRONT = {"in_network": 1_500, "self_pay": 2_750}  # public pricing: pay the year upfront, 2 months free
ONE_OFF = {"Longevity Labs": ("Longevity Labs, annual panel (from)", 350),
           "BYO Labs Review": ("BYO Labs Review, one-time visit", 250)}  # public pricing
VISITS_PER_YEAR = 5
TYPICAL_COPAY = {"in_network": 40, "self_pay": 0}  # self-pay visits are included in the higher membership (illustrative)
SPECIALTY_LABS = (0, 350)  # some members add specialty tests not in the fee; range, illustrative
WAIT_DAYS = {"NY": 9, "CA": 11, "TX": 16, "FL": 14, "WA": 12, "OR": 12}  # invented
DEFAULT_WAIT = 18
# Parsley is in-network with select commercial plans nationwide; not with Medicare, Medicare Advantage, Medicaid or Medi-Cal.


@dataclass
class Quote:
    product: str
    state: str
    in_network: bool
    lines: list[dict]
    low: int
    high: int
    monthly_equiv: int
    first_visit_days: int
    notes: list[str]


def quote(product: str, state: str, has_insurance: bool) -> Quote:
    state = state.upper()[:2]
    in_net = has_insurance  # has_insurance means a commercial plan; we confirm the specific plan before payment
    lines, notes = [], []
    if product in MEMBERSHIP:
        key = "in_network" if in_net else "self_pay"
        m = MEMBERSHIP[product][key]
        lines.append({"label": f"Membership ({'in-network' if in_net else 'self-pay'}), 12 months paid monthly", "low": m, "high": m})
        copay = TYPICAL_COPAY[key] * VISITS_PER_YEAR
        if copay:
            lines.append({"label": f"About {VISITS_PER_YEAR} clinician visits, billed to your insurance (typical copay)", "low": copay, "high": copay})
            notes.append("Visit costs depend on your plan's copay and deductible.")
        lines.append({"label": "Specialty lab tests, only if your clinician recommends them", "low": SPECIALTY_LABS[0], "high": SPECIALTY_LABS[1]})
        notes.append(f"Membership is a 12-month commitment. Paying the year upfront is ${ANNUAL_UPFRONT[key]:,} (2 months free). HSA/FSA eligible.")
    else:
        label, price = ONE_OFF[product]
        lines.append({"label": label, "low": price, "high": price})
        notes.append("Self-pay only, not covered by insurance. HSA/FSA eligible.")
    low, high = sum(x["low"] for x in lines), sum(x["high"] for x in lines)
    return Quote(product, state, in_net, lines, low, high, round(high / 12) if product in MEMBERSHIP else high,
                 WAIT_DAYS.get(state, DEFAULT_WAIT), notes)


SPEC = """## Know your cost: launch spec

**Problem.** 82% of people who see pricing leave without starting checkout (invented funnel, 12 weeks). Member reviews point to two
reasons: the total cost isn't clear up front (membership, then visits billed to insurance, then specialty labs), and the wait to be seen.

**Who it's for.** Prospects on the pricing page who haven't started checkout, across all three product lines.

**What we're building.** A step on the pricing page: pick your state and whether you have insurance, and see
- the full first-year cost as a range, line by line, with what's included and what isn't,
- whether you're likely in-network (confirmed before payment),
- the earliest first visit for your state.

**Success metric.** Pricing → checkout started (baseline 17.5%), sized to detect a 10% relative lift: 7,672 people per variant, 5 weeks.

**Guardrails.** Checkout → paid (we mustn't attract people who then balk at checkout), refunds and cancellations within 30 days,
advisor call volume.

**Out of scope for v1.** Live insurance eligibility checks (v2, with RevOps and billing), plan-specific deductibles.

**Risks.** Showing the higher self-pay total could reduce starts for out-of-network prospects; we'll read the result by in-network status.
Cost figures must be approved by RevOps and legal before launch.

**Rollout.** Build weeks 1-7, 50/50 test weeks 8-12 behind the feature flag `know-your-cost`, ship to 100% only if the decision rule says ship.

**Owner map.** PM: spec, test design, readout. Design: the cost table and states. Engineering: the component, flag and events.
RevOps: cost ranges and in-network rules. Clinical ops: appointment availability by state.
"""

EVENTS = [
    {"event": "pricing_viewed", "when": "Pricing page loads", "properties": "product_line, channel, $feature/know-your-cost"},
    {"event": "cost_estimate_started", "when": "Prospect opens Know your cost", "properties": "product_line"},
    {"event": "cost_estimate_shown", "when": "A quote is displayed", "properties": "product_line, state, in_network, low, high, first_visit_days"},
    {"event": "checkout_started", "when": "Checkout opens", "properties": "product_line, plan (monthly|annual), from_estimate (bool)"},
    {"event": "advisor_call_booked", "when": "Advisor call booked", "properties": "product_line, source_surface"},
    {"event": "member_paid", "when": "Payment succeeds (server-side)", "properties": "product_line, plan, value, path (direct|rep)"},
]
