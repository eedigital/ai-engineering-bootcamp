"""Growth Lab: a prototype of the first 90 days as a growth PM, on invented data.

Pages:  /                 the workbench: overview, roadmap, readouts, findings, exec readout, launch, instrumentation
        /know-your-cost   the launch itself, prospect-facing, with PostHog events when POSTHOG_KEY is set
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import exec_readout, funnel, launch, linear, posthog, readouts, roadmap
from .data import PRODUCTS, PROSPECTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("growthlab")

app = FastAPI(title="Growth Lab", version="1.0")
STATIC = Path(__file__).parent / "static"
_hits: dict[str, deque] = defaultdict(deque)
_readout_cache: dict = {"at": 0.0, "value": None}


def _limited(request: Request, bucket: str, limit: int) -> JSONResponse | None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q, now = _hits[f"{bucket}:{ip}"], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        return JSONResponse(status_code=429, content={"error": "Too many requests. Wait a minute."})
    q.append(now)
    return None


@app.get("/health")
def health():
    return {"status": "ok", "posthog": bool(os.getenv("POSTHOG_KEY")), "linear": bool(os.getenv("LINEAR_API_KEY")),
            "ai_providers": os.getenv("LLM_PROVIDERS", "")}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html", media_type="text/html")


@app.get("/know-your-cost", include_in_schema=False)
def know_your_cost():
    html = (STATIC / "know-your-cost.html").read_text().replace("<!--POSTHOG-->", posthog.snippet())
    return HTMLResponse(html)


@app.get("/api/overview")
def overview():
    s = funnel.summary()
    return {"summary": s, "leak": funnel.biggest_leak(), "by_product": funnel.by("product"), "by_channel": funnel.by("channel"),
            "weekly": funnel.weekly(), "products": {k: v["price_note"] for k, v in PRODUCTS.items()}}


@app.get("/api/roadmap")
def api_roadmap():
    return {"horizon_weeks": roadmap.HORIZON_WEEKS, "tests": [roadmap.as_dict(t) for t in roadmap.plan()]}


@app.get("/api/readouts")
def api_readouts():
    return {"rule": readouts.__doc__.split("Decision rule")[1].strip(), "readouts": readouts.all_readouts(), "findings": readouts.findings()}


@app.get("/api/exec")
def api_exec(request: Request, ai: bool = True, refresh: bool = False):
    """The weekly readout. Written by the AI (Claude first, if a key is set) from computed facts, numbers checked in code.
    Cached for an hour so page views don't spend the AI allowance."""
    if ai and not refresh and _readout_cache["value"] and time.time() - _readout_cache["at"] < 3600:
        return _readout_cache["value"]
    if ai and (r := _limited(request, "ai", 6)):
        return r
    out = exec_readout.write(use_ai=ai)
    if ai:
        _readout_cache.update(at=time.time(), value=out)
    return out


@app.get("/api/launch")
def api_launch():
    return {"spec": launch.SPEC, "events": launch.EVENTS, "prospects": PROSPECTS}


@app.get("/api/quote")
def api_quote(product: str = "Complete Care", state: str = "NY", insurance: bool = True):
    if product not in PRODUCTS:
        return JSONResponse(status_code=422, content={"error": "Unknown product line."})
    return launch.quote(product, state, insurance).__dict__


@app.get("/api/instrumentation")
def api_instrumentation():
    return {"events": launch.EVENTS, "queries": posthog.KPI_QUERIES, "posthog_live": bool(os.getenv("POSTHOG_KEY")),
            "flags": {t.id: t.flag for t in roadmap.TESTS}}


@app.post("/api/linear/{test_id}")
def to_linear(test_id: str, request: Request):
    if (r := _limited(request, "linear", 10)):
        return r
    t = next((x for x in roadmap.plan() if x.id == test_id.upper()), None)
    if not t:
        return JSONResponse(status_code=404, content={"error": "No such test."})
    try:
        return linear.create(t)
    except Exception as e:  # noqa: BLE001
        log.warning("linear_failed %s", e)
        title, body = linear.issue_markdown(t)
        return {"created": False, "title": title, "markdown": body, "note": f"Linear didn't accept it ({str(e)[:120]}). Here's the text."}
