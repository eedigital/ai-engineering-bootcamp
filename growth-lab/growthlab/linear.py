"""Send an experiment to Linear as an issue. Uses a personal API key (LINEAR_API_KEY) and, optionally, LINEAR_TEAM_ID.
Without a key, the issue is returned as copy-ready Markdown instead."""

from __future__ import annotations

import os

import httpx

import datetime as dt

from .roadmap import Test

API = "https://api.linear.app/graphql"
WEEK_ONE = dt.date(2026, 11, 16)  # Monday the 90 days start


def week_dates(start_week: int, weeks: int) -> tuple[dt.date, dt.date]:
    a = WEEK_ONE + dt.timedelta(days=(start_week - 1) * 7)
    return a, a + dt.timedelta(days=weeks * 7 - 1)


def issue_markdown(t: Test) -> tuple[str, str]:
    s = t.sized
    title = f"[{t.id}] {'Launch' if t.kind == 'launch' else 'Test'}: {t.name}"
    if t.start_week:
        a, b = week_dates(t.start_week, s["weeks"])
        when = f"weeks {t.start_week}-{t.start_week + s['weeks'] - 1}, {a:%b %d} to {b:%b %d}"
    else:
        when = f"next quarter. {t.defer_reason}"
    body = f"""**Hypothesis.** {t.hypothesis}

**Why we believe it.** {t.evidence}

| | |
|---|---|
| Primary metric | {t.metric} (baseline {s['baseline']:.1%}) |
| Smallest lift worth detecting | {t.mde:.0%} relative |
| Users per variant | {s['per_variant']:,} |
| Duration | {s['weeks']} weeks: {when} |
| Expected value if real | ${s['annual_value']:,.0f} a year; confidence {t.confidence:.0%} |

**Guardrails.** {"; ".join(t.guardrails)}

**Decision rule.** Ship only if the primary metric is significantly better (p < 0.05) and no guardrail is significantly worse. Otherwise call it inconclusive or don't ship, and log the finding.

**Instrumentation.** 50/50 split behind the PostHog feature flag `{t.flag}`. Events: `pricing_viewed`, `checkout_started`, `advisor_call_booked`, `member_paid` (server-side), each carrying `$feature/{t.flag}`.
"""
    return title, body


def create(t: Test) -> dict:
    title, body = issue_markdown(t)
    key = os.getenv("LINEAR_API_KEY")
    if not key:
        return {"created": False, "title": title, "markdown": body, "note": "No LINEAR_API_KEY set, so here's the issue to paste."}
    headers = {"Authorization": key, "Content-Type": "application/json"}
    team = os.getenv("LINEAR_TEAM_ID")
    if not team:
        r = httpx.post(API, json={"query": "{ teams(first: 1) { nodes { id key } } }"}, headers=headers, timeout=20)
        r.raise_for_status()
        team = r.json()["data"]["teams"]["nodes"][0]["id"]
    q = "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { identifier url } } }"
    r = httpx.post(API, json={"query": q, "variables": {"input": {"teamId": team, "title": title, "description": body}}},
                   headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(data["errors"][0].get("message", "Linear error"))
    issue = data["data"]["issueCreate"]["issue"]
    return {"created": True, "identifier": issue["identifier"], "url": issue["url"], "title": title}
