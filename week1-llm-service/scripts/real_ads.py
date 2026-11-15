"""Real job ads, with the employer's own data as the correct answers.

Many companies publish their careers pages through Greenhouse's public Job Board API
(https://developers.greenhouse.io/job-board). Each job comes with the full ad text plus the employer's
structured title, location and, where they publish it, salary range (pay_input_ranges). So:

- the ad text is real, written by the employer, and fetched fresh each run (it's never stored in this repo);
- the correct answers come from the employer's own data, not from anyone writing labels.

Only fields the employer's data covers are scored: title, location, and the salary range when it's also
written in the ad text (the model can't extract a number the ad doesn't contain). Everything else is "*".
"""

from __future__ import annotations

import html
import re

import httpx

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
# Public Greenhouse boards. Any that don't exist or have no jobs are skipped.
BOARDS = ["airbnb", "stripe", "gitlab", "figma", "discord", "cloudflare", "datadog", "robinhood", "coinbase", "dropbox",
          "reddit", "duolingo", "instacart", "pinterest", "lyft", "twitch", "elastic", "mongodb", "asana", "squarespace"]


def text_of(content: str) -> str:
    """The ad as plain text. Greenhouse returns HTML that is itself HTML-escaped."""
    t = html.unescape(html.unescape(content or ""))
    t = re.sub(r"<(br|/p|/li|/h\d|/div)\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _written(amount: int, text: str) -> bool:
    """Is this salary figure written in the ad, as 150,000 / 150.000 / 150000 / 150K?"""
    forms = {f"{amount:,}", f"{amount:,}".replace(",", "."), str(amount)}
    if amount % 1000 == 0:
        forms |= {f"{amount // 1000}k", f"{amount // 1000}K"}
    flat = text.replace(" ", ",").replace(" ", "")
    return any(f.replace(" ", "") in flat for f in forms)


def _locations(name: str) -> list[str] | str:
    if re.fullmatch(r"\s*(n/?a|tbd|various|multiple locations?)?\s*", name or "", re.I):
        return "*"
    parts = [p.strip() for p in re.split(r";|\||•|·| or |\n|/(?! )", name or "") if p.strip()]
    parts = [p for p in parts if not re.fullmatch(r"(remote|hybrid|anywhere|n/?a|various|multiple)(\s*[-–(].*)?", p, re.I)]
    # "US - Remote" -> "US"
    parts = [re.sub(r"\s*[-–]\s*(remote|hybrid).*$", "", p, flags=re.I).strip() or p for p in parts]
    # "San Francisco, CA" -> also accept "San Francisco"
    out = []
    for p in parts:
        out.append(p)
        if "," in p:
            out.append(p.split(",")[0].strip())
    return out or "*"


def expected_for(job: dict, text: str) -> dict:
    exp = {f: "*" for f in ("title", "company", "location", "work_mode", "seniority", "salary_min", "salary_max", "currency", "skills")}
    exp["title"] = [job["title"]] + ([job["title"].split(",")[0].split(" - ")[0].strip()] if re.search(r",| - ", job["title"]) else [])
    exp["location"] = _locations((job.get("location") or {}).get("name", ""))
    ranges = []
    for r in job.get("pay_input_ranges") or []:
        try:
            lo, hi = round(r["min_cents"] / 100), round(r["max_cents"] / 100)
        except (KeyError, TypeError):
            continue
        if lo >= 10_000 and _written(lo, text) and _written(hi, text):  # yearly ranges the ad actually states
            ranges.append((lo, hi, r.get("currency_type")))
    if ranges:
        exp["salary_min"] = sorted({r[0] for r in ranges})
        exp["salary_max"] = sorted({r[1] for r in ranges})
        exp["currency"] = sorted({r[2] for r in ranges if r[2]}) or "*"
    return exp


def page_text(job: dict) -> str:
    """What a person copies from the job page: the title, the location line, then the ad."""
    loc = (job.get("location") or {}).get("name", "")
    return "\n".join(x for x in [job.get("title", ""), f"Location: {loc}" if loc else "", "", text_of(job.get("content", ""))] if x is not None)


def load(n: int = 12, per_board: int = 2, skip: int = 0, timeout: float = 20) -> list[dict]:
    """[{url, board, text, expected}], spread across boards, preferring jobs that publish a salary.
    skip: start further down each board's list, to get a fresh set of ads."""
    out: list[dict] = []
    with httpx.Client(timeout=timeout, headers={"User-Agent": "ai-engineering-bootcamp-benchmark"}) as c:
        for board in BOARDS:
            if len(out) >= n:
                break
            try:
                r = c.get(API.format(board=board), params={"content": "true", "pay_transparency": "true"})
                jobs = r.json().get("jobs", []) if r.status_code == 200 else []
            except (httpx.HTTPError, ValueError):
                continue
            jobs = sorted(jobs, key=lambda j: j.get("id", 0))
            with_pay = [j for j in jobs if j.get("pay_input_ranges")]
            pool = with_pay if len(with_pay) >= skip + per_board else jobs
            picks = pool[skip: skip + per_board]
            for j in picks:
                text = page_text(j)
                if len(text) < 200:
                    continue
                out.append({"url": j.get("absolute_url"), "board": board, "text": text, "expected": expected_for(j, text)})
                if len(out) >= n:
                    break
    return out


if __name__ == "__main__":
    for ad in load(4):
        print(ad["board"], ad["url"], len(ad["text"]), ad["expected"])
