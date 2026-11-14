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

from . import ai, explore, grantsgov, orglookup, rules  # noqa: E402
from .schemas import Assessment, ChecklistRequest, ExploreGrantRequest, ExploreRequest, GrantRequest, SearchRequest  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("grants")

app = FastAPI(title="Grant Finder", version="0.1.0",
              description="Find US federal grants you can apply for, see why, and get a first draft.")

MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "150"))  # the page shows them 20 at a time
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "40"))     # AI calls: these spend the free model quota
FACTS_LIMIT = int(os.getenv("FACTS_LIMIT_PER_MIN", "300"))   # Grants.gov lookups only: cheap
_hits: dict[str, deque] = defaultdict(deque)


def _limited(request: Request, bucket: str = "api", limit: int | None = None) -> JSONResponse | None:
    limit = limit or RATE_LIMIT
    ip = request.client.host if request.client else "unknown"
    q, now = _hits[f"{bucket}:{ip}"], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
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


@app.get("/api/orgs")
def find_org(q: str, request: Request):
    """Type-ahead: find a nonprofit in IRS records to pre-fill the form."""
    if (r := _limited(request, bucket="lookup", limit=90)):
        return r
    if len(q.strip()) < 3:
        return {"results": []}
    try:
        return {"results": orglookup.search(q[:100])}
    except orglookup.LookupError as e:
        log.warning("org_lookup_failed q=%r error=%s", q, e)
        return _error(502, "The nonprofit lookup isn't answering. Fill in the form instead.")


def _collect(queries: list[str], org_type=None) -> JSONResponse | dict:
    """Run each search, de-duplicate, and interleave so no one search term crowds out the rest."""
    seen: dict[str, dict] = {}
    errors = []
    for q in queries:
        try:
            for hit in grantsgov.search(q, org_type):
                g = grantsgov.from_hit(hit)
                if g["id"] not in seen:
                    seen[g["id"]] = {**g, "query": q}
        except grantsgov.GrantsGovError as e:
            errors.append(str(e))
    if not seen and errors:
        return _error(502, "Grants.gov isn't answering right now. Try again in a minute.")
    by_query: dict[str, list] = defaultdict(list)
    for g in seen.values():
        by_query[g["query"]].append(g)
    ordered: list[dict] = []
    groups = list(by_query.values())
    for i in range(max((len(g) for g in groups), default=0)):
        ordered += [g[i] for g in groups if i < len(g)]
    candidates = ordered[:MAX_CANDIDATES]
    log.info("search queries=%s found=%d returned=%d", queries, len(seen), len(candidates))
    return {"queries": queries, "total_found": len(seen), "candidates": candidates}


@app.post("/api/search")
def search(req: SearchRequest, request: Request):
    if (r := _limited(request, bucket="ai")):
        return r
    return _collect(ai.search_queries(req.profile), req.profile.org_type)


@app.post("/api/explore")
def explore_search(req: ExploreRequest, request: Request):
    """Explore by cause: no organization needed."""
    if (r := _limited(request, bucket="facts", limit=FACTS_LIMIT)):
        return r
    return _collect(explore.queries_for(req.causes, req.criteria))


@app.post("/api/explore/grant")
def explore_grant(req: ExploreGrantRequest, request: Request):
    """One grant's eligibility rules, in plain words, with the user's criteria checked against its text."""
    if (r := _limited(request, bucket="ai") if req.brief else _limited(request, bucket="facts", limit=FACTS_LIMIT)):
        return r
    try:
        grant = grantsgov.fetch(req.grant_id)
    except grantsgov.GrantsGovError:
        return _error(502, "Couldn't load this grant from Grants.gov.")
    out = {
        "grant": grant,
        "who": explore.who_can_apply(grant),
        "mentions": explore.criteria_mentions(grant, req.criteria),
        "amount_note": explore.amount_note(grant, req.amount_needed),
        "brief": None,
        "provider": None,
    }
    if not req.brief:
        return out
    try:
        out["brief"], out["provider"] = explore.brief(grant)
    except explore.AIError as e:
        # The code-checked facts above still stand; the page shows them without the summary.
        log.warning("brief_failed grant=%s error=%s", req.grant_id, e)
    return out


@app.post("/api/assess")
def assess(req: GrantRequest, request: Request):
    if (r := _limited(request, bucket="ai")):
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


@app.post("/api/checklist")
def checklist(req: ChecklistRequest, request: Request):
    """How to apply: standard federal steps (fixed, from code) plus this grant's own items (AI, quote-checked)."""
    if (r := _limited(request, bucket="ai")):
        return r
    try:
        grant = grantsgov.fetch(req.grant_id)
    except grantsgov.GrantsGovError:
        return _error(502, "Couldn't load this grant from Grants.gov.")
    out = {"grant": grant, "standard": explore.STANDARD_STEPS, "specific": [], "ai_ok": True}
    try:
        out["specific"] = explore.checklist(grant).items
    except explore.AIError as e:
        log.warning("checklist_failed grant=%s error=%s", req.grant_id, e)
        out["ai_ok"] = False
    return out


@app.post("/api/draft")
def draft(req: GrantRequest, request: Request):
    if (r := _limited(request, bucket="ai")):
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
