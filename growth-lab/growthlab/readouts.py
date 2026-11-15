"""Readouts for finished tests, and the decision rule, written down before the data is in.

The first three tests to finish are simulated from the invented funnel so the format can be shown end to end:
one clear win, one that wins on its metric but harms a guardrail, and one that is inconclusive.

Decision rule (in this order):
1. Sample ratio mismatch (p < 0.01 on the 50/50 split) -> invalid, fix the setup and rerun.
2. Primary metric significantly better and no guardrail significantly worse -> ship.
3. Primary metric significantly better but a guardrail significantly worse -> don't ship as is; iterate.
4. Primary metric significantly worse -> don't ship.
5. Otherwise -> inconclusive. Say which effects the confidence interval rules out, keep control, and log the learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import stats

ALPHA = 0.05


@dataclass
class Metric:
    name: str
    control_n: int
    control_conv: int
    variant_n: int
    variant_conv: int
    higher_is_better: bool = True

    def read(self) -> stats.Readout:
        return stats.compare(self.control_n, self.control_conv, self.variant_n, self.variant_conv, ALPHA)


@dataclass
class Result:
    test_id: str
    name: str
    weeks: str
    primary: Metric
    guardrails: list[Metric] = field(default_factory=list)
    context: str = ""


RESULTS = [
    Result("T3", "Shorter intake quiz (12 → 6 questions)", "Weeks 1-2",
           Metric("Quiz → saw pricing", 5_204, 3_241, 5_188, 3_437),
           [Metric("Pricing → paid (direct)", 3_241, 383, 3_437, 401), Metric("Switched product line within 30 days", 383, 9, 401, 10, False)],
           "Removed six questions that never changed the recommended product line."),
    Result("T8", "Paid social: symptom-led landing pages", "Weeks 1-2",
           Metric("Session → quiz started", 7_481, 1_349, 7_455, 1_403),
           [Metric("Quiz → paid", 1_349, 52, 1_403, 55)],
           "Three landing pages (fatigue, gut, hormones) matched to the ad that sent the visitor."),
    Result("T7", "Upload-first landing for BYO Labs Review", "Weeks 3-5",
           Metric("Session → quiz started", 5_822, 1_446, 5_869, 1_642),
           [Metric("Started → paid", 1_446, 162, 1_642, 138), Metric("Uploads that couldn't be read", 610, 31, 1_005, 118, False)],
           "Opened with an upload box instead of an explainer."),
]


def _fmt(x: float) -> str:
    return f"{x * 100:.1f}%"


def judge(r: Result) -> dict:
    p = r.primary.read()
    guards = []
    harmed = []
    for g in r.guardrails:
        gr = g.read()
        worse = (gr.diff < 0) if g.higher_is_better else (gr.diff > 0)
        sig_worse = worse and gr.p_value < ALPHA
        guards.append({"name": g.name, "control": gr.rate_c, "variant": gr.rate_v, "lift": gr.lift, "p_value": gr.p_value,
                       "harmed": sig_worse})
        if sig_worse:
            harmed.append(g.name)
    if p.srm_p < 0.01:
        verdict, why = "Invalid", f"The split isn't 50/50 (sample ratio mismatch, p = {p.srm_p:.4f}). Fix assignment and rerun."
    elif p.p_value < ALPHA and p.diff > 0 and not harmed:
        verdict, why = "Ship", f"{r.primary.name} rose from {_fmt(p.rate_c)} to {_fmt(p.rate_v)} ({p.lift:+.1%} relative, p = {p.p_value:.3f}). No guardrail got worse."
    elif p.p_value < ALPHA and p.diff > 0:
        verdict, why = "Don't ship as is", (f"{r.primary.name} rose {p.lift:+.1%} (p = {p.p_value:.3f}), but {' and '.join(harmed)} got significantly worse. "
                                           "The win doesn't survive the guardrail; iterate on the variant.")
    elif p.p_value < ALPHA:
        verdict, why = "Don't ship", f"{r.primary.name} fell {p.lift:+.1%} (p = {p.p_value:.3f})."
    else:
        verdict, why = "Inconclusive", (f"{r.primary.name}: {_fmt(p.rate_c)} vs {_fmt(p.rate_v)} ({p.lift:+.1%}, p = {p.p_value:.2f}). "
                                       f"The 95% interval for the difference runs from {p.ci_low * 100:+.2f} to {p.ci_high * 100:+.2f} points, "
                                       f"so a lift above {p.ci_high / p.rate_c:.0%} is unlikely and a small harm isn't ruled out. Keep control.")
    return {"test_id": r.test_id, "name": r.name, "weeks": r.weeks, "context": r.context, "verdict": verdict, "why": why,
            "primary": {"name": r.primary.name, "control": p.rate_c, "variant": p.rate_v, "lift": p.lift, "p_value": p.p_value,
                        "ci_low": p.ci_low, "ci_high": p.ci_high, "control_n": p.control_n, "variant_n": p.variant_n, "srm_p": p.srm_p},
            "guardrails": guards}


def all_readouts() -> list[dict]:
    return [judge(r) for r in RESULTS]


# --- findings library: what each test taught, kept whatever the verdict ---------------------------

FINDINGS = {
    "T3": ("Fewer questions, same fit", "Half the quiz didn't change the recommendation. Removing it raised the share reaching pricing "
           "without more people switching product line later. Next: test whether the remaining questions can personalise the pricing page."),
    "T8": ("Ad-matched pages aren't enough on their own", "Matching the landing page to the ad didn't move quiz starts detectably. "
           "The paid social gap is likely audience quality, not the page. Next: test audience targeting and creative, with cost per paid member as the metric."),
    "T7": ("More starts, worse starts", "Leading with an upload box brought in more people, but more uploads couldn't be read and fewer starters paid. "
           "Next: accept the common lab formats only, and say which ones before the upload."),
}


def findings() -> list[dict]:
    out = []
    for r in all_readouts():
        title, body = FINDINGS[r["test_id"]]
        out.append({"test_id": r["test_id"], "title": title, "learning": body, "verdict": r["verdict"], "test": r["name"]})
    return out
