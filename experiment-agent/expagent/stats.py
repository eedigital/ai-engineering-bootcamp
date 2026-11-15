"""Sample size and test duration for an A/B test on a conversion rate. Plain maths, no AI.

Two-sided test of two proportions (normal approximation), the standard formula used by most
online calculators:

    n per variant = ( z(1-α/2)·√(2·p̄·(1-p̄)) + z(1-β)·√(p1(1-p1) + p2(1-p2)) )² / (p2 - p1)²

where p1 is the baseline rate, p2 = p1 × (1 + MDE) the rate you want to be able to detect,
and p̄ = (p1 + p2) / 2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

_Z = NormalDist().inv_cdf


@dataclass(frozen=True)
class Plan:
    baseline: float          # e.g. 0.032 for 3.2%
    mde_relative: float      # e.g. 0.10 for a 10% relative lift
    alpha: float
    power: float
    variants: int            # including control
    per_variant: int
    total: int
    daily_traffic: int | None
    traffic_share: float     # share of traffic in the test
    days: int | None
    days_rounded: int | None  # rounded up to whole weeks, to cover weekday/weekend cycles

    @property
    def target(self) -> float:
        return self.baseline * (1 + self.mde_relative)


def per_variant(baseline: float, mde_relative: float, alpha: float = 0.05, power: float = 0.80) -> int:
    if not 0 < baseline < 1:
        raise ValueError("baseline must be between 0 and 1 (e.g. 0.032 for 3.2%)")
    if mde_relative == 0:
        raise ValueError("the minimum detectable effect can't be zero")
    p1, p2 = baseline, baseline * (1 + mde_relative)
    if not 0 < p2 < 1:
        raise ValueError("baseline × (1 + effect) must stay between 0 and 1")
    pbar = (p1 + p2) / 2
    num = _Z(1 - alpha / 2) * math.sqrt(2 * pbar * (1 - pbar)) + _Z(power) * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return math.ceil(num ** 2 / (p2 - p1) ** 2)


def plan(baseline: float, mde_relative: float, daily_traffic: int | None = None, alpha: float = 0.05,
         power: float = 0.80, variants: int = 2, traffic_share: float = 1.0) -> Plan:
    n = per_variant(baseline, mde_relative, alpha, power)
    total = n * variants
    days = rounded = None
    if daily_traffic and daily_traffic > 0:
        days = math.ceil(total / (daily_traffic * traffic_share))
        rounded = max(7, math.ceil(days / 7) * 7)
    return Plan(baseline, mde_relative, alpha, power, variants, n, total, daily_traffic, traffic_share, days, rounded)
