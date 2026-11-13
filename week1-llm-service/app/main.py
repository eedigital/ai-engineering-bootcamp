"""Week 1: a live LLM service with structured outputs and guardrails."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()  # reads .env locally; on Render the dashboard sets env vars (existing vars are never overridden)

from .extractor import ExtractionError, extract
from .guardrails import check_input
from .schemas import ExtractRequest, ExtractResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("week1")

app = FastAPI(
    title="Job Post Extractor",
    description="Week 1 of the AI Engineering Bootcamp: messy text in, validated JSON out.",
    version="0.1.0",
)

# --- tiny in-memory rate limit: protects your free LLM quota from one noisy caller ---
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


INDEX_HTML = Path(__file__).parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
def root():
    """The human-friendly page. Developers can still use /docs."""
    return FileResponse(INDEX_HTML, media_type="text/html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "providers": os.getenv("LLM_PROVIDERS", "gemini,groq,ollama")}


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(req: ExtractRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        return JSONResponse(
            status_code=429,
            content=ExtractResponse(ok=False, error=f"rate limit: {RATE_LIMIT} requests/minute").model_dump(),
        )

    guard = check_input(req.text)
    if not guard.ok:
        log.info("blocked_input reason=%s", guard.reason)
        return JSONResponse(status_code=422, content=ExtractResponse(ok=False, error=guard.reason).model_dump())

    try:
        posting, meta = extract(guard.text)
    except ExtractionError as e:
        # Safe fallback: a clear error, never a stack trace or a half-valid object.
        log.warning("extraction_failed attempts=%d error=%s", e.attempts, e)
        # Say which stage failed. Provider errors are status codes only, never keys.
        msg = str(e) if str(e).startswith("model unavailable") else "model output failed validation"
        return JSONResponse(
            status_code=502,
            content=ExtractResponse(ok=False, error=msg, attempts=e.attempts).model_dump(),
        )

    return ExtractResponse(ok=True, data=posting, redactions=guard.redactions, **meta)
