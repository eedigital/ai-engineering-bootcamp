"""Compare prompt versions on quality, speed and cost, and say which one to ship and why."""

from __future__ import annotations

from pydantic import BaseModel, Field

OVERFIT_GAP = 0.3  # open cases this much better than held-out ones (and 2+ held-out misses) = probably fitted to the test


class Result(BaseModel):
    version: int = Field(ge=1, le=4)
    case_id: str = Field(max_length=40)
    heldout: bool = False
    passed: bool | None = None  # None = the call failed, so there's nothing to score
    latency_ms: float | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class Prices(BaseModel):
    """US dollars per million tokens, as the provider lists them."""
    input: float = Field(ge=0, le=1000)
    output: float = Field(ge=0, le=1000)


def _rate(passed: int, scored: int) -> float | None:
    return passed / scored if scored else None


def _pct(r: float | None) -> str:
    return "n/a" if r is None else f"{round(r * 100)}%"


def summarise(results: list[Result], prices: Prices | None = None) -> dict:
    versions: dict[int, list[Result]] = {}
    for r in results:
        versions.setdefault(r.version, []).append(r)

    rows = []
    for v in sorted(versions):
        rs = versions[v]
        scored = [r for r in rs if r.passed is not None]
        dev = [r for r in scored if not r.heldout]
        held = [r for r in scored if r.heldout]
        timed = [r.latency_ms for r in scored if r.latency_ms is not None]
        ins = [r.input_tokens for r in scored if r.input_tokens is not None]
        outs = [r.output_tokens for r in scored if r.output_tokens is not None]
        avg_in = sum(ins) / len(ins) if ins else None
        avg_out = sum(outs) / len(outs) if outs else None
        cost = None
        if prices and avg_in is not None and avg_out is not None:
            cost = round((avg_in * prices.input + avg_out * prices.output) / 1_000_000 * 1000, 4)  # per 1,000 calls
        row = {
            "version": v,
            "cases": len(rs),
            "scored": len(scored),
            "errors": len(rs) - len(scored),
            "passed": sum(r.passed for r in scored),
            "pass_rate": _rate(sum(r.passed for r in scored), len(scored)),
            "open_pass_rate": _rate(sum(r.passed for r in dev), len(dev)),
            "heldout_pass_rate": _rate(sum(r.passed for r in held), len(held)),
            "avg_latency_ms": round(sum(timed) / len(timed)) if timed else None,
            "avg_tokens": round(avg_in + avg_out) if avg_in is not None and avg_out is not None else None,
            "cost_per_1000": cost,
            "overfit": False,
        }
        t, h = row["open_pass_rate"], row["heldout_pass_rate"]
        held_misses = sum(not r.passed for r in held)
        if t is not None and h is not None and held_misses >= 2 and t - h >= OVERFIT_GAP:
            row["overfit"] = True  # one miss in a small held-out set is noise, not overfitting
        rows.append(row)

    return {"versions": rows, **_verdict(rows)}


def _tiebreak(a: dict, b: dict) -> str:
    """Why `a` beat `b` when both passed the same share of cases."""
    if a["cost_per_1000"] is not None and b["cost_per_1000"] is not None and a["cost_per_1000"] < b["cost_per_1000"]:
        return "and costs less per call."
    if a["avg_tokens"] is not None and b["avg_tokens"] is not None and a["avg_tokens"] < b["avg_tokens"]:
        return "and uses fewer tokens per call."
    if a["avg_latency_ms"] is not None and b["avg_latency_ms"] is not None and a["avg_latency_ms"] < b["avg_latency_ms"]:
        return "and answers faster."
    return "and they're even on cost and speed."


def _verdict(rows: list[dict]) -> dict:
    ranked = [r for r in rows if r["pass_rate"] is not None]
    if not ranked:
        return {"winner": None, "why": "No version finished a call, so there is nothing to compare yet."}

    def key(r: dict):
        # Quality first. Then cost when prices are known, else tokens (what cost is made of), then speed.
        spend = r["cost_per_1000"] if r["cost_per_1000"] is not None else r["avg_tokens"]
        return (-r["pass_rate"], spend if spend is not None else float("inf"),
                r["avg_latency_ms"] if r["avg_latency_ms"] is not None else float("inf"))

    ranked.sort(key=key)
    best = ranked[0]
    why = f"V{best['version']} passed {best['passed']} of {best['scored']} cases ({_pct(best['pass_rate'])})."
    others = [f"V{r['version']} passed {r['passed']} ({_pct(r['pass_rate'])})" for r in ranked[1:]]
    if others:
        why += " " + ", ".join(others) + "."
    if len(ranked) > 1 and ranked[1]["pass_rate"] == best["pass_rate"]:
        why += f" It ties with V{ranked[1]['version']} on quality, " + _tiebreak(best, ranked[1])
    notes = []
    if best["heldout_pass_rate"] is not None:
        notes.append(f"On held-out cases it scored {_pct(best['heldout_pass_rate'])}.")
    if best["overfit"]:
        notes.append("It does much better on the open cases than on the held-out ones, so it may be fitted to the test.")
    if any(r["errors"] for r in rows):
        notes.append("Some calls failed and weren't scored.")
    return {"winner": best["version"], "why": " ".join([why, *notes])}
