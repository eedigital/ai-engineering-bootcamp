"""Prompt Lab: write prompt versions, run them on test cases, and ship the one that wins on quality, cost and speed.

The page runs one case at a time (/api/run), so results fill in live and no request waits on a whole grid.
Scoring is code; the AI only writes answers and, when asked, a rewritten prompt.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

from . import compare, improve, runner  # noqa: E402
from .models import Case  # noqa: E402
from .samples import SAMPLES  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("promptlab")

app = FastAPI(title="Prompt Lab", version="0.1.0",
              description="Test prompt versions on real cases and compare quality, cost and speed.")

STATIC = Path(__file__).parent / "static"
PER_IP = int(os.getenv("AI_LIMIT_PER_MIN", "100"))  # run, improve, run again with 3 versions = 61 calls
ALL_IPS = int(os.getenv("AI_LIMIT_TOTAL_PER_MIN", "120"))  # keeps free-tier quotas safe from one busy minute
_hits: dict[str, deque] = defaultdict(deque)


def _limited(request: Request, bucket: str, limit: int, total: int | None = None) -> JSONResponse | None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    keys = [(f"{bucket}:{ip}", limit)] + ([(f"{bucket}:*", total)] if total else [])
    for key, cap in keys:
        q = _hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= cap:
            return JSONResponse(status_code=429, content={"error": "Too many requests. Wait a minute and try again."})
    for key, _ in keys:
        _hits[key].append(now)
    return None


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=6000)
    case: Case
    output: Literal["json", "text"]
    provider: str | None = Field(default=None, max_length=20)


class CompareRequest(BaseModel):
    results: list[compare.Result] = Field(min_length=1, max_length=80)
    prices: compare.Prices | None = None


class ImproveRequest(BaseModel):
    task: str = Field(min_length=1, max_length=600)
    output: Literal["json", "text"]
    prompt: str = Field(min_length=1, max_length=6000)
    failures: list[improve.Failure] = Field(min_length=1, max_length=12)
    passing: int = Field(default=0, ge=0, le=20)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html", media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok", "providers": [p["name"] for p in runner.providers()]}


@app.get("/api/samples")
def samples():
    return {"tasks": [t.model_dump() for t in SAMPLES]}


@app.get("/api/providers")
def providers():
    return {"providers": runner.providers()}


@app.post("/api/run")
def run(req: RunRequest, request: Request):
    allowed = {p["name"] for p in runner.providers()}
    if req.provider is not None and req.provider not in allowed:
        return _error(422, f"'{req.provider}' isn't available here. Choose one of: {', '.join(sorted(allowed)) or 'none'}.")
    if (r := _limited(request, "ai", PER_IP, ALL_IPS)):
        return r
    result = runner.run_case(req.prompt, req.case, req.output, req.provider)
    log.info("run case=%s provider=%s passed=%s ms=%s", req.case.id, result.get("provider"), result["passed"],
             result.get("latency_ms"))
    return result


@app.post("/api/compare")
def compare_versions(req: CompareRequest):
    return compare.summarise(req.results, req.prices)


@app.post("/api/improve")
def improve_prompt(req: ImproveRequest, request: Request):
    if (r := _limited(request, "ai", PER_IP, ALL_IPS)):
        return r
    try:
        out = improve.suggest(req.task, req.output, req.prompt, req.failures, req.passing)
    except ValueError as e:
        return _error(422, str(e))
    except improve.StructuredError as e:
        log.warning("improve_failed error=%s", e)
        return _error(502, "The AI is busy or gave an answer that didn't fit. Try again in a minute.")
    return out
