"""The 90-day CRO roadmap: hypotheses grounded in the funnel and in member reviews, sized with real power maths,
and sequenced so tests on the same surface never overlap and the biggest expected impact goes first.

Each test's baseline comes from the invented funnel (funnel.py); sample size from stats.per_variant; weeks from the
weekly traffic on that surface. Expected impact = extra paid members a week if the lift is real x first-year value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import funnel, stats
from .data import PRODUCTS

HORIZON_WEEKS = 13  # ~90 days


@dataclass
class Test:
    id: str
    name: str
    surface: str              # landing | quiz | pricing | checkout | advisor
    product: str | None       # None = all product lines
    hypothesis: str
    evidence: str             # why we believe it: research, data, reviews
    metric: str               # primary metric
    metric_step: tuple[str, str]  # (from, to) step keys in the funnel
    mde: float                # smallest relative lift worth detecting
    guardrails: list[str]
    kind: str = "test"        # test | launch
    status: str = "planned"
    confidence: float = 0.5   # how likely the lift is real (0-1), for prioritising
    effort: int = 2           # 1 small, 2 medium, 3 large
    flag: str = ""            # feature flag key in PostHog
    sized: dict = field(default_factory=dict)
    start_week: int | None = None
    defer_reason: str = ""


TESTS = [
    Test("T1", "Know your cost before checkout", "pricing", None,
         "If we show each person's full first-year cost (membership, visits billed to insurance, labs) and their in-network status "
         "on the pricing page, then more will start checkout, because cost uncertainty is why they stop.",
         "Biggest leak in the funnel is pricing → checkout (17.5%). Reviews cite surprise costs and a 12-month commitment.",
         "Pricing → checkout started", ("pricing_viewed", "checkout_started"), 0.10,
         ["Paid conversion (checkout → paid)", "Refund or cancellation within 30 days", "Advisor call volume"],
         kind="launch", confidence=0.6, effort=3),
    Test("T2", "Show the earliest appointment date", "pricing", "Complete Care",
         "If we show 'first visit as early as <date>' next to Complete Care pricing, then more will start checkout, "
         "because people fear paying monthly while waiting weeks to be seen.",
         "Wait time is the lowest-rated part of reviews (Zocdoc wait time 1.0/5).",
         "Pricing → checkout started", ("pricing_viewed", "checkout_started"), 0.15,
         ["Visits booked within 21 days of joining", "Paid conversion"], confidence=0.55, effort=1),
    Test("T3", "Shorter intake quiz (12 → 6 questions)", "quiz", None,
         "If we cut the quiz to the 6 questions that change the recommendation, more people will reach pricing.",
         "Quiz → pricing is 62%; session replays (to confirm) show drop-off on questions 7-12.",
         "Quiz → saw pricing", ("quiz_started", "pricing_viewed"), 0.05,
         ["Paid conversion from pricing", "Product-line fit (switches after joining)"], confidence=0.6, effort=1),
    Test("T4", "Annual price shown as monthly", "pricing", "Complete Care",
         "If we lead with the monthly price instead of the annual total, more will start checkout.",
         "Common pattern in subscription pricing; risk of shifting people to monthly plans.",
         "Pricing → checkout started", ("pricing_viewed", "checkout_started"), 0.10,
         ["Share of annual plans", "Revenue per visitor", "Paid conversion"], confidence=0.45, effort=1),
    Test("T5", "Talk to an advisor, always visible", "pricing", "Complete Care",
         "If a 'Talk to an advisor' button stays visible on pricing, more undecided people will book a call and join with a rep.",
         "Rep-assisted members close at a high rate once a call is held, but few book.",
         "Pricing → advisor call booked", ("pricing_viewed", "advisor_call_booked"), 0.25,
         ["Direct checkout rate (cannibalisation)", "Advisor capacity (calls per rep per day)"], confidence=0.5, effort=1),
    Test("T6", "HSA/FSA and Apple Pay at checkout", "checkout", "Longevity Labs",
         "If Longevity Labs checkout shows HSA/FSA eligibility and Apple Pay, more checkouts will complete.",
         "Lab buyers often pay with pre-tax accounts; card entry is the slowest step on mobile.",
         "Checkout → paid", ("checkout_started", "paid_direct"), 0.12,
         ["Payment failures", "Chargebacks"], confidence=0.55, effort=2),
    Test("T7", "Upload-first landing for BYO Labs Review", "landing", "BYO Labs Review",
         "If the BYO Labs landing page starts with 'Upload your results' instead of an explainer, more will start.",
         "Visitors arrive with results in hand from other lab platforms.",
         "Session → quiz started", ("sessions", "quiz_started"), 0.10,
         ["Paid conversion", "Uploads that can't be read"], confidence=0.5, effort=2),
    Test("T8", "Paid social: symptom-led landing pages", "landing", "Complete Care",
         "If paid social traffic lands on a page for the symptom in the ad (fatigue, gut, hormones), more will start the quiz.",
         "Paid social converts at a third of referral; the generic homepage doesn't match the ad's promise.",
         "Session → quiz started", ("sessions", "quiz_started"), 0.10,
         ["Cost per paid member", "Paid conversion"], confidence=0.5, effort=2),
]


# The roadmap as created in Linear (project P-EED-1)
LINEAR_ISSUES = {"T3": "EED-5", "T8": "EED-6", "T2": "EED-7", "T6": "EED-8", "T7": "EED-9", "T1": "EED-10", "T4": "EED-11", "T5": "EED-12"}
LINEAR_BASE = "https://linear.app/eedigital/issue/"

FLAGS = {'T1': 'know-your-cost', 'T2': 'earliest-appointment', 'T3': 'short-quiz', 'T4': 'monthly-price', 'T5': 'sticky-advisor', 'T6': 'hsa-applepay', 'T7': 'byo-upload-first', 'T8': 'symptom-landing'}
for _t in TESTS:
    _t.flag = FLAGS[_t.id]


def _baseline(t: Test) -> tuple[float, float]:
    """(baseline rate, weekly users entering the test)"""
    s = funnel.summary(product=t.product)
    tot = s["totals"]
    a, b = t.metric_step
    return (tot[b] / tot[a] if tot[a] else 0.0), tot[a] / 12


def size(t: Test) -> dict:
    base, weekly = _baseline(t)
    n = stats.per_variant(base, t.mde)
    weeks = max(1, math.ceil(2 * n / weekly)) if weekly else 99
    weeks = max(2, weeks)  # always at least two full weeks
    # impact: extra paid members a week if the lift is real, valued at first-year value
    s = funnel.summary(product=t.product)
    value = (s["revenue"] / s["totals"]["paid"]) if s["totals"]["paid"] else 0
    tot = s["totals"]
    end = t.metric_step[1]
    # share of people at the metric's end step who go on to pay, along the path they're on
    paid_after = {"advisor_call_booked": tot["paid_rep"], "checkout_started": tot["paid_direct"], "paid_direct": tot["paid_direct"]}.get(end, tot["paid"])
    downstream = paid_after / tot[end] if tot[end] else 0
    extra_paid = weekly * base * t.mde * downstream
    return {"baseline": base, "weekly_users": weekly, "per_variant": n, "weeks": weeks, "extra_paid_per_week": extra_paid,
            "annual_value": extra_paid * 52 * value, "expected_value": extra_paid * 52 * value * t.confidence,
            "priority": extra_paid * 52 * value * t.confidence / t.effort}


def plan() -> list[Test]:
    """Size every test, then schedule: highest priority first, one test per surface (and product) at a time."""
    tests = [Test(**{**t.__dict__}) for t in TESTS]
    for t in tests:
        t.sized = size(t)
    busy: dict[tuple, int] = {}  # (surface, product or 'all') -> next free week
    for t in sorted(tests, key=lambda x: -x.sized["priority"]):
        keys = [(t.surface, t.product or "all")] + ([(t.surface, "all")] if t.product else [(t.surface, p) for p in PRODUCTS])
        start = max([1] + [busy.get(k, 1) for k in keys])
        if start + t.sized["weeks"] - 1 <= HORIZON_WEEKS:
            t.start_week = start
            for k in keys:
                busy[k] = start + t.sized["weeks"]
        else:
            t.status = "next quarter"
            t.defer_reason = (f"Needs {t.sized['weeks']} weeks of traffic to detect a {t.mde:.0%} lift, more than the 13-week horizon."
                              if t.sized["weeks"] > HORIZON_WEEKS else
                              f"The {t.surface} page is taken by higher-priority tests until week {start}; "
                              f"this {t.sized['weeks']}-week test wouldn't finish by week {HORIZON_WEEKS}.")
    return sorted(tests, key=lambda x: (x.start_week or 99, -x.sized["priority"]))


def as_dict(t: Test) -> dict:
    d = {k: v for k, v in t.__dict__.items()}
    d["end_week"] = (t.start_week + t.sized["weeks"] - 1) if t.start_week else None
    issue = LINEAR_ISSUES.get(t.id)
    d["linear"] = {"id": issue, "url": LINEAR_BASE + issue} if issue else None
    return d
