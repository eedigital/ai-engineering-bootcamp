"""Grant Finder: describe your organization, get eligible federal grants and a first draft.

Flow: /api/search (fast list) -> /api/assess per grant (rules, then AI) -> /api/draft.
The page calls /api/assess a few at a time so results appear as they're checked.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()

from . import ai, grantsgov, rules  # noqa: E402
from .schemas import Assessment, GrantRequest, SearchRequest  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("grants")

app = FastAPI(title="Grant Finder", version="0.1.0",
              description="Find US federal grants you can apply for, see why, and get a first draft.")

MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "10"))
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "40"))
_hits: dict[str, deque] = defaultdict(deque)


def _limited(request: Request) -> JSONResponse | None:
    ip = request.client.host if request.client else "unknown"
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return JSONResponse(status_code=429, content={"error": "Too many requests. Wait a minute and try again."})
    q.append(now)
    return None


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html", media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/search")
def search(req: SearchRequest, request: Request):
    if (r := _limited(request)):
        return r
    queries = ai.search_queries(req.profile)
    seen: dict[str, dict] = {}
    errors = []
    for q in queries:
        try:
            for hit in grantsgov.search(q, req.profile.org_type):
                g = grantsgov.from_hit(hit)
                if g["id"] not in seen:
                    seen[g["id"]] = {**g, "query": q}
        except grantsgov.GrantsGovError as e:
            errors.append(str(e))
    if not seen and errors:
        return _error(502, "Grants.gov isn't answering right now. Try again in a minute.")
    # Interleave queries so one search term can't crowd out the others.
    by_query: dict[str, list] = defaultdict(list)
    for g in seen.values():
        by_query[g["query"]].append(g)
    ordered = [g for group in zip(*by_query.values()) for g in group] if by_query else []
    leftovers = [g for g in seen.values() if g not in ordered]
    candidates = (ordered + leftovers)[:MAX_CANDIDATES]
    log.info("search queries=%s found=%d returned=%d", queries, len(seen), len(candidates))
    return {"queries": queries, "total_found": len(seen), "candidates": candidates}


@app.post("/api/assess")
def assess(req: GrantRequest, request: Request):
    if (r := _limited(request)):
        return r
    try:
        grant = grantsgov.fetch(req.grant_id)
    except grantsgov.GrantsGovError:
        return _error(502, "Couldn't load this grant from Grants.gov.")
    rule_result = rules.check(req.profile, grant)
    if rule_result.status == "ineligible":
        # No AI call needed: code already knows the answer. Saves quota and can't be wrong.
        a = Assessment(verdict="not_eligible", fit_score=0, summary=rule_result.reasons[0])
        return {"grant": grant, "rules": rule_result, "assessment": a, "provider": None}
    try:
        a, provider = ai.assess(req.profile, grant, rule_result)
    except ai.AIError as e:
        log.warning("assess_failed grant=%s error=%s", req.grant_id, e)
        return _error(502, "The AI services are busy. This grant will be retried.")
    return {"grant": grant, "rules": rule_result, "assessment": a, "provider": provider}


@app.post("/api/draft")
def draft(req: GrantRequest, request: Request):
    if (r := _limited(request)):
        return r
    try:
        grant = grantsgov.fetch(req.grant_id)
    except grantsgov.GrantsGovError:
        return _error(502, "Couldn't load this grant from Grants.gov.")
    try:
        d, provider = ai.draft(req.profile, grant)
    except ai.AIError as e:
        log.warning("draft_failed grant=%s error=%s", req.grant_id, e)
        return _error(502, "The AI services are busy. Try the draft again in a minute.")
    return {"grant": grant, "draft": d, "provider": provider}
