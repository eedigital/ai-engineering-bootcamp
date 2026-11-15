"""The weekly exec readout, written by Claude from numbers the code computed, and checked before it's shown.

1. Code computes the facts (funnel, CVR direct and rep-assisted, revenue, test verdicts, what's next).
2. Claude writes a short readout for the SVP of Growth from those facts only.
3. Code checks every number in Claude's text appears in the facts (allowing the usual rounding). If one doesn't,
   the readout is rejected and the template version is shown instead, with a note saying so.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field

from . import funnel, readouts, roadmap

log = logging.getLogger("growthlab")


PROGRAM_WEEK = 5  # the readout is written as of week 5 of the 90 days, after the first three tests finished
PROGRAM_WEEKS = 13


def facts(week: int = 12) -> dict:
    """week: the latest week of funnel data. The programme is at PROGRAM_WEEK of 13."""
    now = funnel.summary(weeks=(week, week))
    prev = funnel.summary(weeks=(week - 1, week - 1))
    q = funnel.summary(weeks=(week - 3, week))
    leak = funnel.biggest_leak()
    done = readouts.all_readouts()
    plan = roadmap.plan()
    read = {r["test_id"] for r in done}
    running = [t for t in plan if t.start_week and t.id not in read and t.start_week <= PROGRAM_WEEK]
    upcoming = [t for t in plan if t.start_week and t.id not in read and t.start_week > PROGRAM_WEEK]
    return {
        "program_week": PROGRAM_WEEK, "program_weeks": 13,
        "cvr_pct": round(now["cvr"] * 100, 2), "cvr_prev_pct": round(prev["cvr"] * 100, 2),
        "cvr_direct_pct": round(now["cvr_direct"] * 100, 2), "cvr_rep_pct": round(now["cvr_rep"] * 100, 3),
        "rep_share_pct": round(now["rep_share"] * 100, 1),
        "new_members": now["totals"]["paid"], "new_members_prev": prev["totals"]["paid"],
        "revenue": round(now["revenue"]), "revenue_prev": round(prev["revenue"]),
        "revenue_4wk": round(q["revenue"]),
        "leak": f"{leak['from']} → {leak['to']}", "leak_rate_pct": round(leak["rate"] * 100, 1), "leak_lost_per_week": round(leak["lost_per_week"]),
        "tests": [{"id": r["test_id"], "name": r["name"], "verdict": r["verdict"], "lift_pct": round(r["primary"]["lift"] * 100, 1),
                   "p_value": "<0.001" if r["primary"]["p_value"] < 0.001 else round(r["primary"]["p_value"], 3),
                   "guardrails_harmed": [{"name": g["name"], "control_pct": round(g["control"] * 100, 1),
                                          "variant_pct": round(g["variant"] * 100, 1)} for g in r["guardrails"] if g["harmed"]]}
                  for r in done],
        "running": [{"id": t.id, "name": t.name, "ends_week": t.start_week + t.sized["weeks"] - 1} for t in running],
        "next": [{"id": t.id, "name": t.name, "start_week": t.start_week, "weeks": t.sized["weeks"]} for t in upcoming],
        "deferred": [{"id": t.id, "name": t.name, "weeks_needed": t.sized["weeks"],
                      "why": "needs more weeks of traffic than the quarter has" if t.sized["weeks"] > PROGRAM_WEEKS
                      else "its page is taken by higher-priority tests"} for t in plan if not t.start_week],
    }


def template(f: dict) -> str:
    direction = "up" if f["cvr_pct"] >= f["cvr_prev_pct"] else "down"
    def _why(t: dict) -> str:
        g = t.get("guardrails_harmed") or []
        return (" (" + " and ".join(f"{x['name']} fell from {x['control_pct']}% to {x['variant_pct']}%" if x['variant_pct'] < x['control_pct']
                                    else f"{x['name']} rose from {x['control_pct']}% to {x['variant_pct']}%" for x in g) + ")") if g else ""
    tests = "; ".join(f"{t['id']} {t['name']}: {t['verdict']}{_why(t)}" for t in f["tests"])
    running = "; ".join(f"{t['id']} {t['name']} (ends week {t['ends_week']})" for t in f["running"])
    nxt = "; ".join(f"{t['id']} {t['name']} (starts week {t['start_week']}, {t['weeks']} weeks)" for t in f["next"])
    deferred = "; ".join(f"{t['id']} {t['name']} ({t['why']}, {t['weeks_needed']} weeks)" for t in f["deferred"])
    return (f"**Week {f['program_week']} of {f['program_weeks']}.** CVR {f['cvr_pct']}% ({direction} from {f['cvr_prev_pct']}%), {f['new_members']} new members, "
            f"${f['revenue']:,} first-year revenue. Rep-assisted is {f['rep_share_pct']}% of new members.\n\n"
            f"**Biggest leak:** {f['leak']}, only {f['leak_rate_pct']}% continue, about {f['leak_lost_per_week']:,} people a week. "
            f"That's what Know your cost targets.\n\n**Tests read out:** {tests}.\n\n**Running:** {running}.\n\n**Next:** {nxt}."
            + (f"\n\n**Decision needed:** {deferred}. Neither can be read in the 90 days. Move them to next quarter, or accept a larger minimum effect where traffic is the limit." if deferred else ""))


class Readout(BaseModel):
    headline: str = Field(max_length=200, description="One sentence: the most important thing this week")
    body: str = Field(max_length=1400, description="3 short paragraphs: numbers, what the tests showed, what's next and any decision needed")
    decision_needed: str = Field(default="", max_length=300, description="A decision the SVP needs to make, or empty")


SYSTEM = """You write the weekly growth readout for the SVP of Growth at a healthcare membership company.
Use ONLY the numbers in the facts JSON, written exactly as they appear there (you may add % or $ and thousands separators).
Don't calculate new numbers. Plain words, short sentences, no hype. Call an inconclusive test inconclusive.
If a deferred test needs a decision (e.g. more traffic), say so in decision_needed.
When a test has guardrails_harmed, say which guardrail got worse and by how much: that is why it does not ship.
Say where we are as "week N of 13". Write a p-value of "<0.001" as "p < 0.001".
Keep the body under 150 words: what changed this week, what we learned, what's running next. An SVP reads it in one minute."""

_NUM = re.compile(r"(?<![A-Za-z])\$?\d[\d,]*(?:\.\d+)?")


def _numbers_in(obj) -> set[float]:
    out: set[float] = set()
    for m in _NUM.findall(json.dumps(obj)):
        try:
            out.add(round(float(m.replace("$", "").replace(",", "")), 3))
        except ValueError:
            pass
    return out


def unsupported_numbers(text: str, f: dict) -> list[str]:
    """Numbers in the text that aren't in the facts (test ids like T3 and week numbers are in the facts too)."""
    allowed = _numbers_in(f) | {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 100.0}
    text = text.replace("the 90 days", "the quarter")  # fixed phrase in the template, not a data claim
    bad = []
    for m in _NUM.findall(text):
        v = round(float(m.replace("$", "").replace(",", "")), 3)
        if v not in allowed and not any(abs(v - a) <= 0.051 for a in allowed if a < 1000):
            bad.append(m)
    return bad


def write(week: int = 12, use_ai: bool = True) -> dict:
    f = facts(week)
    if use_ai:
        try:
            from llm.structured import StructuredError, ask_json
            r, provider = ask_json(SYSTEM, "<facts>\n" + json.dumps(f) + "\n</facts>", Readout, temperature=0.2)
            text = f"**{r.headline}**\n\n{r.body}" + (f"\n\n**Decision needed:** {r.decision_needed}" if r.decision_needed else "")
            bad = unsupported_numbers(text, f)
            if not bad:
                return {"markdown": text, "source": provider, "facts": f, "checked": True}
            log.warning("readout_rejected unsupported=%s", bad)
            return {"markdown": template(f), "source": "template", "facts": f, "checked": True,
                    "note": f"The AI's draft used numbers that aren't in the data ({', '.join(bad[:5])}), so the template is shown."}
        except (ImportError, StructuredError) as e:
            log.warning("readout_ai_unavailable %s", e)
    return {"markdown": template(f), "source": "template", "facts": f, "checked": True,
            "note": "The AI is unavailable, so this is the template version."}
