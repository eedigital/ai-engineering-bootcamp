"""Funnel analysis: conversion by step, direct vs rep-assisted, by product line and channel, and revenue.

KPIs from the role: CVR (direct and rep-assisted) and revenue. CVR here is paid sign-ups per session.
"""

from __future__ import annotations

from collections import defaultdict

from .data import PRODUCTS, REP_STEPS, STEPS, Row, rows

LABELS = {"sessions": "Sessions", "quiz_started": "Started the quiz", "pricing_viewed": "Saw pricing",
          "checkout_started": "Started checkout", "paid_direct": "Paid (direct)", "advisor_call_booked": "Booked advisor call",
          "advisor_call_held": "Advisor call held", "paid_rep": "Paid (rep-assisted)"}


def _sum(rs: list[Row]) -> dict:
    t = defaultdict(int)
    for r in rs:
        for k in STEPS + REP_STEPS:
            t[k] += getattr(r, k)
    t["paid"] = t["paid_direct"] + t["paid_rep"]
    return dict(t)


def _rev(rs: list[Row]) -> float:
    return sum(r.paid * PRODUCTS[r.product]["value"] for r in rs)


def summary(weeks: tuple[int, int] | None = None, product: str | None = None, channel: str | None = None) -> dict:
    rs = [r for r in rows() if (not weeks or weeks[0] <= r.week <= weeks[1]) and (not product or r.product == product)
          and (not channel or r.channel == channel)]
    t = _sum(rs)
    s = t["sessions"] or 1
    steps = []
    prev = None
    for k in STEPS:
        steps.append({"key": k, "label": LABELS[k], "count": t[k], "of_sessions": t[k] / s,
                      "from_prev": (t[k] / t[prev]) if prev and t[prev] else None})
        prev = k
    rep = [{"key": k, "label": LABELS[k], "count": t[k]} for k in REP_STEPS]
    revenue = _rev(rs)
    return {"totals": t, "steps": steps, "rep_steps": rep, "cvr": t["paid"] / s, "cvr_direct": t["paid_direct"] / s,
            "cvr_rep": t["paid_rep"] / s, "rep_share": t["paid_rep"] / t["paid"] if t["paid"] else 0,
            "revenue": revenue, "revenue_per_session": revenue / s,
            "rep_close_rate": t["paid_rep"] / t["advisor_call_held"] if t["advisor_call_held"] else 0}


def biggest_leak(product: str | None = None) -> dict:
    """The step that loses the most people who got that far."""
    st = summary(product=product)["steps"]
    worst = min((x for x in st if x["from_prev"] is not None), key=lambda x: x["from_prev"])
    i = [x["key"] for x in st].index(worst["key"])
    return {"from": st[i - 1]["label"], "to": worst["label"], "rate": worst["from_prev"], "lost_per_week": (st[i - 1]["count"] - worst["count"]) / 12}


def by(dimension: str) -> list[dict]:
    keys = PRODUCTS if dimension == "product" else sorted({r.channel for r in rows()})
    out = []
    for k in keys:
        s = summary(product=k) if dimension == "product" else summary(channel=k)
        out.append({"name": k, "sessions": s["totals"]["sessions"], "cvr": s["cvr"], "cvr_direct": s["cvr_direct"], "cvr_rep": s["cvr_rep"],
                    "paid": s["totals"]["paid"], "revenue": s["revenue"], "revenue_per_session": s["revenue_per_session"]})
    return out


def weekly() -> list[dict]:
    out = []
    for w in range(1, 13):
        s = summary(weeks=(w, w))
        out.append({"week": w, "sessions": s["totals"]["sessions"], "paid": s["totals"]["paid"], "cvr": s["cvr"],
                    "cvr_direct": s["cvr_direct"], "cvr_rep": s["cvr_rep"], "revenue": s["revenue"]})
    return out


def weekly_surface_traffic() -> dict:
    """Average weekly users reaching each surface, for sizing tests."""
    t = summary()["totals"]
    return {"landing": t["sessions"] / 12, "quiz": t["quiz_started"] / 12, "pricing": t["pricing_viewed"] / 12,
            "checkout": t["checkout_started"] / 12, "advisor": (t["pricing_viewed"] - t["checkout_started"]) / 12}
