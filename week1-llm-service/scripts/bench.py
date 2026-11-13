"""Measure the numbers your Week 1 README needs.

    python week1-llm-service/scripts/bench.py --url http://localhost:8000 --n 50
    python week1-llm-service/scripts/bench.py --url https://<your-app>.onrender.com --n 50

Reports: success rate, validation-failure rate, repair rate, median and p90 latency.
Free tiers are rate limited, so --sleep spaces the calls out (default 4s).
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import time
from pathlib import Path

import httpx

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "job_posts.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--sleep", type=float, default=4.0)
    args = ap.parse_args()

    posts = [json.loads(line)["text"] for line in SAMPLES.read_text().splitlines() if line.strip()]
    rows = []
    for i, text in zip(range(args.n), itertools.cycle(posts)):
        t0 = time.perf_counter()
        r = httpx.post(f"{args.url}/extract", json={"text": text}, timeout=90)
        wall = (time.perf_counter() - t0) * 1000
        body = r.json()
        rows.append({"status": r.status_code, "ok": body.get("ok"), "attempts": body.get("attempts", 0), "ms": wall})
        print(f"{i + 1:>3}/{args.n}  HTTP {r.status_code}  attempts={body.get('attempts')}  {wall:,.0f} ms")
        time.sleep(args.sleep)

    n = len(rows)
    ok = [r for r in rows if r["ok"]]
    lat = sorted(r["ms"] for r in ok) or [0]
    print("\n| Metric | Value |\n| --- | --- |")
    print(f"| Calls | {n} |")
    print(f"| Success rate | {len(ok) / n:.0%} |")
    print(f"| Validation failures (502) | {sum(r['status'] == 502 for r in rows) / n:.0%} |")
    print(f"| Needed a repair re-prompt | {sum(r['attempts'] == 2 for r in ok) / max(len(ok), 1):.0%} |")
    print(f"| Rate limited (429) | {sum(r['status'] == 429 for r in rows)} |")
    print(f"| Median latency | {statistics.median(lat):,.0f} ms |")
    print(f"| p90 latency | {lat[int(0.9 * (len(lat) - 1))]:,.0f} ms |")


if __name__ == "__main__":
    main()
