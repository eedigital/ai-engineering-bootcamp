"""Deal Desk: get one export deal right. A concept prototype built to plug into ICC One Click.

Integration points (see /integrate and the README):
- Launch link:  /?product=...&origin=...&destination=...&value=...&currency=...&mode=...&buyer=...
- Embed:        <script src="https://<host>/embed.js" data-target="#deal-desk"></script>
- AI tools:     GET /api/tools returns function definitions an AI assistant can call
- API:          POST /api/plan (rules only, no AI), POST /api/read (AI reads buyer text)
"""

from __future__ import annotations

import io
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

load_dotenv()

from . import ai, rules  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("dealdesk")

app = FastAPI(
    title="Deal Desk API",
    version="0.1.0",
    description="Concept prototype for ICC One Click: Incoterms® 2020 rule, payment method, documents and a draft terms sheet "
                "for one export deal. Not an official ICC product. Incoterms® is a registered trademark of ICC.",
)

# One Click (or any partner site) can call the API from the browser. Tighten to known origins in production.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])

STATIC = Path(__file__).parent / "static"
AI_LIMIT = int(os.getenv("AI_LIMIT_PER_MIN", "20"))
_hits: dict[str, deque] = defaultdict(deque)


def _limited(request: Request, bucket: str, limit: int) -> JSONResponse | None:
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
    return FileResponse(STATIC / "index.html", media_type="text/html")


@app.get("/integrate", include_in_schema=False)
def integrate():
    return FileResponse(STATIC / "integrate.html", media_type="text/html")


@app.get("/embed.js", include_in_schema=False)
def embed_js():
    return FileResponse(STATIC / "embed.js", media_type="application/javascript")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/plan")
def plan(deal: rules.Deal, request: Request):
    """The deal plan: Incoterms® rule, payment method, documents and draft terms. Plain rules, no AI, instant."""
    if (r := _limited(request, "plan", 120)):
        return r
    return rules.plan(deal)


@app.post("/api/read")
async def read(request: Request, text: str | None = Form(default=None), file: UploadFile | None = File(default=None)):
    """Read a buyer's order, quote or email (pasted text, PDF or .txt) and return the deal it describes plus red flags."""
    if (r := _limited(request, "ai", AI_LIMIT)):
        return r
    body = (text or "").strip()
    if file is not None:
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            return _error(422, "That file is over 10 MB.")
        name = (file.filename or "").lower()
        if name.endswith(".pdf") or data[:5] == b"%PDF-":
            try:
                from pypdf import PdfReader
                body = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages[:20])
            except Exception:
                return _error(422, "That PDF couldn't be read. Paste the text instead.")
        elif name.endswith((".txt", ".eml", ".csv")):
            body = data.decode("utf-8", errors="replace")
        else:
            return _error(422, "Upload a PDF or a .txt file, or paste the text.")
    if len(body) < 20:
        return _error(422, "Paste the buyer's message or order: at least a sentence or two.")
    try:
        reading = ai.read(body)
    except ai.StructuredError as e:
        log.warning("read_failed error=%s", e)
        return _error(502, "The AI reader is busy. You can still fill in the deal yourself.")
    return reading


@app.get("/api/tools")
def tools(request: Request):
    """Function definitions an AI assistant (such as One Click's) can call. OpenAI-style tool schema."""
    base = str(request.base_url).rstrip("/")
    deal_schema = rules.Deal.model_json_schema()
    return {
        "tools": [
            {"type": "function", "function": {
                "name": "deal_desk_plan",
                "description": "Recommend the Incoterms® 2020 rule, a payment method, the documents and a draft terms sheet for "
                               "one export deal. Deterministic rules, not AI. Use when an SME asks how to ship, price or get paid for a specific deal.",
                "parameters": deal_schema}},
            {"type": "function", "function": {
                "name": "deal_desk_read",
                "description": "Read a foreign buyer's order, quote or email and return the deal details it states plus risky terms, each quoted from the text.",
                "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "The buyer's message or order"}}, "required": ["text"]}}},
        ],
        "endpoints": {"deal_desk_plan": f"POST {base}/api/plan (JSON body)", "deal_desk_read": f"POST {base}/api/read (form field 'text')"},
        "launch_link": f"{base}/?product=&origin=&destination=&value=&currency=&mode=&buyer=",
    }
