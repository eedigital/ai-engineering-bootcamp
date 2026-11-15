"""Measure the numbers your Week 1 README needs: accuracy, reliability and speed.

    python week1-llm-service/scripts/bench.py --url http://localhost:8000 --n 16
    python week1-llm-service/scripts/bench.py --url https://<your-app>.onrender.com --n 16 --out results.md

Accuracy: each sample post has a hand-written expected answer in samples/expected.jsonl. A field is correct
when it matches. Where a post is genuinely ambiguous, the expected value is a list of acceptable answers,
or "*" (not scored). Text fields match if one contains the other, ignoring case and punctuation, so
"Mid-level DevOps Engineer" matches "DevOps Engineer". Skills score by recall: every expected skill must be found.

Reliability and speed: success rate, validation failures, repair re-prompts, rate limits, median and p90 latency.
Free tiers are rate limited, so --sleep spaces the calls out (default 4s).
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    # the 8 posts used while building and fixing: good for catching regressions, too familiar to judge accuracy
    "dev": (ROOT / "samples" / "job_posts.jsonl", ROOT / "samples" / "expected.jsonl"),
    # 15 posts kept aside: never used to change the code, so their score is the honest one
    "heldout": (ROOT / "samples" / "heldout_posts.jsonl", ROOT / "samples" / "heldout_expected.jsonl"),
}
FIELDS = ["title", "company", "location", "work_mode", "seniority", "salary_min", "salary_max", "currency", "skills"]


def _norm(v) -> str:
    return re.sub(r"[^a-z0-9#+]+", "", str(v).lower())


def field_ok(field: str, got, want) -> bool | None:
    """True/False, or None when the field isn't scored for this post."""
    if want == "*":
        return None
    if field == "skills":
        have = {_norm(s) for s in (got or [])}
        return all(_norm(s) in have or any(_norm(s) in h for h in have) for s in want)
    options = want if isinstance(want, list) else [want]
    for w in options:
        if w is None and got in (None, "", []):
            return True
        if w is None or got in (None, ""):
            continue
        if isinstance(w, (int, float)):
            if got == w:
                return True
        elif field in ("title", "company", "location"):
            a, b = _norm(got), _norm(w)
            if a and b and (a in b or b in a):
                return True
        elif _norm(got) == _norm(w):
            return True
    return False


def score(data: dict, expected: dict) -> dict[str, bool | None]:
    return {f: field_ok(f, (data or {}).get(f), expected[f]) for f in FIELDS}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--sleep", type=float, default=4.0)
    ap.add_argument("--out", help="also write the report to this Markdown file")
    ap.add_argument("--set", choices=list(SETS), default="dev", help="dev: the posts used while fixing; heldout: never-seen posts")
    args = ap.parse_args()

    posts_file, expected_file = SETS[args.set]
    posts = [json.loads(line)["text"] for line in posts_file.read_text().splitlines() if line.strip()]
    expected = [json.loads(line) for line in expected_file.read_text().splitlines() if line.strip()]
    if args.n <= 0:
        args.n = len(posts)
    rows = []
    for i, (k, text) in zip(range(args.n), itertools.cycle(enumerate(posts))):
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{args.url}/extract", json={"text": text}, timeout=90)
            status, body = r.status_code, r.json()
        except (httpx.HTTPError, ValueError) as e:
            status, body = 0, {"error": str(e)}
        wall = (time.perf_counter() - t0) * 1000
        marks = score(body.get("data"), expected[k]) if body.get("ok") else {}
        rows.append({"post": k, "status": status, "ok": body.get("ok"), "attempts": body.get("attempts", 0), "ms": wall,
                     "provider": body.get("provider"), "marks": marks, "data": body.get("data"), "error": body.get("error")})
        wrong = [f for f, m in marks.items() if m is False]
        print(f"{i + 1:>3}/{args.n}  post {k + 1}  HTTP {status}  {body.get('provider') or '-':<7} attempts={body.get('attempts')}  "
              f"{wall:,.0f} ms  {'wrong: ' + ', '.join(wrong) if wrong else ('all correct' if marks else body.get('error', ''))}")
        time.sleep(args.sleep)

    n = len(rows)
    ok = [r for r in rows if r["ok"]]
    lat = sorted(r["ms"] for r in ok) or [0]
    scored = [(f, m) for r in ok for f, m in r["marks"].items() if m is not None]
    acc = sum(m for _, m in scored) / len(scored) if scored else 0
    perfect = sum(all(m is not False for m in r["marks"].values()) for r in ok)
    providers = {p: sum(r["provider"] == p for r in ok) for p in sorted({r["provider"] for r in ok if r["provider"]})}

    lines = [f"Run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC against {args.url}, {n} calls over {len(posts)} posts "
             f"({'held-out: never used to change the code' if args.set == 'heldout' else 'dev set: the posts used while fixing'}).", "",
             "| Metric | Value |", "| --- | --- |",
             f"| Field accuracy | {acc:.0%} ({sum(m for _, m in scored)}/{len(scored)} fields) |",
             f"| Posts with every field right | {perfect}/{len(ok)} |",
             f"| Success rate | {len(ok) / n:.0%} |",
             f"| Validation failures (502) | {sum(r['status'] == 502 for r in rows) / n:.0%} |",
             f"| Needed a repair re-prompt | {sum(r['attempts'] == 2 for r in ok) / max(len(ok), 1):.0%} |",
             f"| Rate limited (429) | {sum(r['status'] == 429 for r in rows)} |",
             f"| Answered by | {', '.join(f'{p} {c}' for p, c in providers.items()) or '-'} |",
             f"| Median latency | {statistics.median(lat):,.0f} ms |",
             f"| p90 latency | {lat[int(0.9 * (len(lat) - 1))]:,.0f} ms |",
             "", "Accuracy by field:", "", "| Field | Right |", "| --- | --- |"]
    for f in FIELDS:
        ms = [r["marks"][f] for r in ok if r["marks"].get(f) is not None]
        if ms:
            lines.append(f"| {f} | {sum(ms)}/{len(ms)} |")
    misses = [(r["post"] + 1, f, r["data"].get(f), expected[r["post"]][f]) for r in ok for f, m in r["marks"].items() if m is False]
    if misses:
        lines += ["", "What it got wrong:", "", "| Post | Field | Got | Expected |", "| --- | --- | --- | --- |"]
        seen = set()
        for p, f, got, want in misses:
            if (p, f, json.dumps(got)) in seen:
                continue
            seen.add((p, f, json.dumps(got)))
            lines.append(f"| {p} | {f} | {json.dumps(got, ensure_ascii=False)} | {json.dumps(want, ensure_ascii=False)} |")
    fails = [r for r in rows if not r["ok"]]
    if fails:
        lines += ["", "Failed calls:", ""] + [f"- post {r['post'] + 1}: HTTP {r['status']}: {str(r['error'])[:200]}" for r in fails]
    report = "\n".join(lines)
    print("\n" + report)
    if args.out:
        Path(args.out).write_text(report + "\n")


if __name__ == "__main__":
    main()
