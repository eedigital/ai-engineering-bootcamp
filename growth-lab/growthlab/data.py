"""Invented data for the prototype: 12 weeks of a membership sign-up funnel, three product lines, four channels.

Nothing here is Parsley's real data. Prices follow Parsley's public pricing (checked 15 Nov 2026) (Complete Care:
$150/month in-network, $275/month self-pay) and are invented where it isn't (Longevity Labs, BYO Labs Review).
Rates are plausible for a considered-purchase healthcare membership and deliberately include the problem the
prototype is about: many people reach the pricing page and stop.

Generated from a fixed seed, so every run and every test sees the same numbers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache

WEEKS = 12
SEED = 20261115

PRODUCTS = {
    # name: share of sessions, first-year value (USD), step rates for the direct path, rep-assisted rates
    "Complete Care": {"share": 0.60, "value": 2_400, "price_note": "Blend of in-network $150/mo and self-pay $275/mo, 12 months (public pricing)",
                      "start": 0.18, "pricing": 0.58, "checkout": 0.12, "paid": 0.46, "book": 0.050, "held": 0.70, "rep_paid": 0.38},
    "Longevity Labs": {"share": 0.25, "value": 350, "price_note": "From $350/year, self-pay (public pricing)",
                       "start": 0.22, "pricing": 0.66, "checkout": 0.20, "paid": 0.58, "book": 0.015, "held": 0.72, "rep_paid": 0.30},
    "BYO Labs Review": {"share": 0.15, "value": 250, "price_note": "$250 one-time, self-pay (public pricing)",
                        "start": 0.25, "pricing": 0.70, "checkout": 0.24, "paid": 0.62, "book": 0.010, "held": 0.75, "rep_paid": 0.28},
}
CHANNELS = {"Paid search": 0.34, "Paid social": 0.26, "Organic": 0.28, "Referral": 0.12}
CHANNEL_QUALITY = {"Paid search": 1.05, "Paid social": 0.70, "Organic": 1.10, "Referral": 1.45}  # multiplies late-funnel rates
WEEKLY_SESSIONS = 26_000

STEPS = ["sessions", "quiz_started", "pricing_viewed", "checkout_started", "paid_direct"]
REP_STEPS = ["advisor_call_booked", "advisor_call_held", "paid_rep"]


@dataclass(frozen=True)
class Row:
    week: int
    product: str
    channel: str
    sessions: int
    quiz_started: int
    pricing_viewed: int
    checkout_started: int
    paid_direct: int
    advisor_call_booked: int
    advisor_call_held: int
    paid_rep: int

    @property
    def paid(self) -> int:
        return self.paid_direct + self.paid_rep


def _binom(rng: random.Random, n: int, p: float) -> int:
    """Binomial draw; normal approximation for large n keeps generation fast."""
    p = min(max(p, 0.0), 1.0)
    if n < 60:
        return sum(rng.random() < p for _ in range(n))
    mean, sd = n * p, (n * p * (1 - p)) ** 0.5
    return max(0, min(n, round(rng.gauss(mean, sd))))


@lru_cache(maxsize=1)
def rows() -> tuple[Row, ...]:
    rng = random.Random(SEED)
    out = []
    for w in range(1, WEEKS + 1):
        season = 1 + 0.04 * ((w % 4) - 1.5) / 1.5  # small weekly wobble
        for prod, cfg in PRODUCTS.items():
            for ch, share in CHANNELS.items():
                q = CHANNEL_QUALITY[ch]
                s = _binom(rng, round(WEEKLY_SESSIONS * season * cfg["share"] * share / 0.5), 0.5)
                qs = _binom(rng, s, cfg["start"])
                pv = _binom(rng, qs, cfg["pricing"])
                co = _binom(rng, pv, cfg["checkout"] * q)
                pd = _binom(rng, co, cfg["paid"] * min(q, 1.2))
                bk = _binom(rng, pv - co, cfg["book"] * q)
                hd = _binom(rng, bk, cfg["held"])
                pr = _binom(rng, hd, cfg["rep_paid"] * min(q, 1.2))
                out.append(Row(w, prod, ch, s, qs, pv, co, pd, bk, hd, pr))
    return tuple(out)


# --- invented people, for the launch demo ------------------------------------------------------

PROSPECTS = [
    {"id": "maya", "name": "Maya R.", "age": 34, "state": "NY", "insurance": "Aetna", "in_network": True,
     "goal": "Fatigue and brain fog for two years; normal labs from her PCP", "product": "Complete Care"},
    {"id": "dev", "name": "Dev P.", "age": 41, "state": "TX", "insurance": "None (HSA)", "in_network": False,
     "goal": "Wants a longevity baseline; already wears a CGM", "product": "Longevity Labs"},
    {"id": "lena", "name": "Lena K.", "age": 29, "state": "CA", "insurance": "Blue Shield", "in_network": True,
     "goal": "Bloating and irregular cycles; has Function Health results", "product": "BYO Labs Review"},
    {"id": "sam", "name": "Sam O.", "age": 66, "state": "FL", "insurance": "Medicare (not accepted)", "in_network": False,
     "goal": "Pre-diabetes; doctor said 'watch it'", "product": "Complete Care"},
]
