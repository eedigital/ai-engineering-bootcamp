"""Check a deck's numbers with plain code. Investors spot inconsistent numbers instantly,
and this is arithmetic, so it shouldn't be left to an AI.

Finds money and metric mentions on each slide, then flags:
- the same metric stated with different values on different slides
- market sizes out of order (TAM should be >= SAM >= SOM)
- use-of-funds percentages that don't add up to about 100%
- no clear funding ask anywhere in the deck
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .deck import Slide

# metric name -> words that introduce it
METRICS: dict[str, list[str]] = {
    "TAM": ["tam", "total addressable market"],
    "SAM": ["sam", "serviceable addressable market", "serviceable available market"],
    "SOM": ["som", "serviceable obtainable market"],
    "ARR": ["arr", "annual recurring revenue", "annual revenue"],
    "MRR": ["mrr", "monthly recurring revenue", "monthly revenue"],
    "Revenue": ["revenue"],
    "Raise": ["raising", "we are raising", "we're raising", "seeking", "the ask", "our ask", "investment of"],
    "Burn": ["burn", "monthly burn", "burn rate"],
    "Runway": ["runway"],
    "Customers": ["customers", "paying customers", "clients"],
    "Users": ["users", "active users", "mau", "dau"],
}

_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "trillion": 1e12}
MONEY = re.compile(r"[$€£]\s?(\d[\d,]*(?:\.\d+)?)\s?(k|m|mm|b|bn|t|thousand|million|billion|trillion)?\b", re.I)
COUNT = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s?(k|m|thousand|million)?\+?\s+(paying customers|customers|clients|active users|users)\b", re.I)
MONTHS = re.compile(r"\b(\d{1,2})\s*(?:-|to)?\s*(?:\d{1,2}\s*)?months?\b", re.I)
PERCENT = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s?%")


@dataclass
class Mention:
    metric: str
    value: float
    slide: int
    text: str  # the exact words on the slide


def _num(s: str, mult: str | None) -> float:
    return float(s.replace(",", "")) * _MULT.get((mult or "").lower(), 1)


def fmt(v: float, money: bool = True) -> str:
    p = "$" if money else ""
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= div:
            return f"{p}{v / div:.3g}{suf}"
    return f"{p}{v:,.0f}"


def _metric_near(line: str, pos: int) -> str | None:
    """The metric word closest before the number on the same line (within ~60 chars), else after it."""
    low = line.lower()
    before = low[max(0, pos - 60):pos]
    best, best_dist = None, 10**9
    for metric, words in METRICS.items():
        for w in words:
            for m in re.finditer(rf"\b{re.escape(w)}\b", before):
                dist = len(before) - m.end()
                if dist < best_dist:
                    best, best_dist = metric, dist
    if best:
        return best
    after = low[pos:pos + 40]
    for metric, words in METRICS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", after) for w in words):
            return metric
    return None


def mentions(slides: list[Slide]) -> list[Mention]:
    out: list[Mention] = []
    for s in slides:
        for line in s.text.splitlines():
            for m in MONEY.finditer(line):
                metric = _metric_near(line, m.start())
                if metric and metric not in ("Customers", "Users", "Runway"):
                    out.append(Mention(metric, _num(m.group(1), m.group(2)), s.number, m.group(0).strip()))
            for m in COUNT.finditer(line):
                metric = "Customers" if "customer" in m.group(3).lower() or "client" in m.group(3).lower() else "Users"
                out.append(Mention(metric, _num(m.group(1), m.group(2)), s.number, m.group(0).strip()))
            if "runway" in line.lower():
                m = MONTHS.search(line)
                if m:
                    out.append(Mention("Runway", float(m.group(1)), s.number, m.group(0).strip()))
    return out


def check(slides: list[Slide]) -> dict:
    found = mentions(slides)
    issues: list[dict] = []

    # 1. Same metric, different values on different slides (more than 5% apart).
    by_metric: dict[str, list[Mention]] = {}
    for m in found:
        by_metric.setdefault(m.metric, []).append(m)
    for metric, ms in by_metric.items():
        values = {round(m.value, -2) if m.value >= 1000 else m.value for m in ms}
        slides_seen = {m.slide for m in ms}
        if len(values) > 1 and len(slides_seen) > 1:
            lo, hi = min(m.value for m in ms), max(m.value for m in ms)
            if hi > lo * 1.05:
                where = "; ".join(f"slide {m.slide}: “{m.text}”" for m in sorted(ms, key=lambda x: x.slide))
                issues.append({"kind": "mismatch", "metric": metric,
                               "message": f"{metric} is stated differently on different slides ({where}). Pick one figure and use it everywhere.",
                               "slides": sorted(slides_seen)})

    # 2. Market sizing order.
    first = {k: by_metric[k][0] for k in ("TAM", "SAM", "SOM") if k in by_metric}
    pairs = [("TAM", "SAM"), ("SAM", "SOM"), ("TAM", "SOM")]
    for big, small in pairs:
        if big in first and small in first and first[small].value > first[big].value:
            issues.append({"kind": "market_order", "metric": f"{big}/{small}",
                           "message": f"{small} ({fmt(first[small].value)}) is bigger than {big} ({fmt(first[big].value)}). {small} should be a slice of {big}.",
                           "slides": sorted({first[big].slide, first[small].slide})})
    if "TAM" in first and "SOM" not in first and "SAM" not in first:
        issues.append({"kind": "market_only_tam", "metric": "SAM/SOM",
                       "message": "Only a total market (TAM) is given. Investors also want the part you can realistically reach (SAM) and win (SOM).",
                       "slides": [first["TAM"].slide]})

    # 3. Use of funds should add to ~100%.
    for s in slides:
        low = s.text.lower()
        if any(w in low for w in ("use of funds", "use of proceeds", "allocation")):
            pcts = [float(p) for p in PERCENT.findall(s.text)]
            if len(pcts) >= 2 and not 95 <= sum(pcts) <= 105:
                issues.append({"kind": "funds_sum", "metric": "Use of funds",
                               "message": f"The use-of-funds percentages on slide {s.number} add up to {sum(pcts):g}%, not 100%.",
                               "slides": [s.number]})

    # 4. Is there an ask?
    has_ask = "Raise" in by_metric or any(
        re.search(r"\b(raising|the ask|our ask|seeking|pre-seed|seed round|series a)\b", s.text, re.I) for s in slides)
    if not has_ask:
        issues.append({"kind": "no_ask", "metric": "Raise",
                       "message": "The deck never says how much you're raising. State the amount and the round clearly, usually near the end.",
                       "slides": []})

    # 5. Runway sanity: raise / burn vs stated runway.
    if "Raise" in by_metric and "Burn" in by_metric and "Runway" in by_metric:
        implied = by_metric["Raise"][0].value / by_metric["Burn"][0].value
        stated = by_metric["Runway"][0].value
        if abs(implied - stated) > max(3, stated * 0.3):
            issues.append({"kind": "runway", "metric": "Runway",
                           "message": f"Raising {fmt(by_metric['Raise'][0].value)} at {fmt(by_metric['Burn'][0].value)} a month burn gives about {implied:.0f} months, but the deck says {stated:g} months.",
                           "slides": sorted({by_metric[k][0].slide for k in ('Raise', 'Burn', 'Runway')})})

    figures = [{"metric": m.metric, "value": m.value, "display": fmt(m.value, m.metric not in ("Customers", "Users", "Runway")) + (" months" if m.metric == "Runway" else ""),
                "slide": m.slide, "text": m.text} for m in found]
    return {"issues": issues, "figures": figures}
