"""Deal Desk: get one export deal right. A concept prototype built to plug into ICC One Click.

Integration points (see /integrate and the README):
- Launch link:  /?text=<the SME's message>  (or the older /?product=...&destination=... fields)
- Embed:        <script src="https://<host>/embed.js" data-target="#deal-desk"></script>
- AI tools:     GET /api/tools returns function definitions an AI assistant can call
- API:          POST /api/start (read a message), POST /api/pack (documents and checks), POST /api/plan, POST /api/read
"""

from __future__ import annotations

import io
import json
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

from . import ai, oneclick, rules  # noqa: E402

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
    """One click: drop in the buyer's message, get a checked deal pack."""
    return FileResponse(STATIC / "oneclick.html", media_type="text/html")


@app.get("/wizard", include_in_schema=False)
def wizard():
    """The original step-by-step planner."""
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


async def _body(text: str | None, file: UploadFile | None, min_len: int = 20) -> str | JSONResponse:
    """The message as text, from the form field or an uploaded PDF or text file."""
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
    if len(body) < min_len:
        return _error(422, "Tell us about the deal: at least a sentence, or paste the buyer's message.")
    return body[:ai.MAX_CHARS]


@app.post("/api/start")
async def start(request: Request, text: str | None = Form(default=None), file: UploadFile | None = File(default=None),
                profile: str | None = Form(default=None), use_ai: bool = Form(default=True)):
    """One click, step 1: read the message, fill in what can be found or worked out, and ask at most three questions.
    Works without AI too: if the AI is busy, plain-code reading still fills in most of the deal."""
    if (r := _limited(request, "start", 60)):
        return r
    body = await _body(text, file, min_len=12)
    if isinstance(body, JSONResponse):
        return body
    try:
        prof = json.loads(profile) if profile else {}
        prof = prof if isinstance(prof, dict) else {}
    except ValueError:
        prof = {}
    reading, notice = None, None
    if use_ai and _limited(request, "ai", AI_LIMIT) is None:
        try:
            reading = ai.read(body).model_dump()
        except ai.StructuredError as e:
            log.warning("start_ai_unavailable error=%s", e)
            notice = "The AI reader is busy, so this was filled in by our built-in reader. Check the details below."
    result = oneclick.start(body, prof, reading)
    if notice:
        result["notice"] = notice
    return result


@app.post("/api/pack")
def make_pack(deal: oneclick.OneDeal, request: Request):
    """One click, step 2: the quotation, proforma invoice and packing list from one set of figures, plus the
    document checklist and the checks. Plain rules, no AI, instant."""
    if (r := _limited(request, "plan", 120)):
        return r
    return oneclick.pack(deal)


@app.post("/api/read")
async def read(request: Request, text: str | None = Form(default=None), file: UploadFile | None = File(default=None)):
    """Read a buyer's order, quote or email (pasted text, PDF or .txt) and return the deal it describes plus red flags."""
    if (r := _limited(request, "ai", AI_LIMIT)):
        return r
    body = await _body(text, file)
    if isinstance(body, JSONResponse):
        return body
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
                "name": "deal_desk_pack",
                "description": "Make the export documents for one deal: a quotation, proforma invoice and packing list from one set of "
                               "figures, the documents to prepare, and checks for mistakes. Deterministic rules, not AI.",
                "parameters": oneclick.OneDeal.model_json_schema()}},
            {"type": "function", "function": {
                "name": "deal_desk_read",
                "description": "Read a foreign buyer's order, quote or email and return the deal details it states plus risky terms, each quoted from the text.",
                "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "The buyer's message or order"}}, "required": ["text"]}}},
        ],
        "endpoints": {"deal_desk_plan": f"POST {base}/api/plan (JSON body)", "deal_desk_pack": f"POST {base}/api/pack (JSON body)",
                      "deal_desk_read": f"POST {base}/api/read (form field 'text')",
                      "one_click_start": f"POST {base}/api/start (form field 'text', optional 'file' and 'profile')"},
        "launch_link": f"{base}/?text=<the user's message, URL-encoded>",
    }
