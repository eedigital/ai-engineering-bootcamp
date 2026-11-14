"""Pitch Perfect: review a startup pitch deck and practice investor questions."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

load_dotenv()

from . import ai, numbers  # noqa: E402
from .deck import DeckError, Slide, parse  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pitch")

app = FastAPI(title="Pitch Perfect", version="0.1.0",
              description="Review a startup pitch deck section by section, check its numbers, and practice investor questions.")

AI_LIMIT = int(os.getenv("AI_LIMIT_PER_MIN", "30"))
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


class DeckRequest(BaseModel):
    slides: list[Slide] = Field(min_length=1, max_length=40)


class QuestionRequest(DeckRequest):
    asked: list[str] = Field(default_factory=list, max_length=50)
    weak: list[str] = Field(default_factory=list, max_length=10)


class GradeRequest(DeckRequest):
    question: str = Field(min_length=5, max_length=400)
    answer: str = Field(min_length=1, max_length=3000)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html", media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/parse")
async def parse_deck(request: Request, file: UploadFile = File(...)):
    """PDF or PowerPoint in, slide text out. The page keeps the slides and sends them with later requests."""
    if (r := _limited(request, "parse", 20)):
        return r
    data = await file.read()
    try:
        slides = parse(file.filename or "", data)
    except DeckError as e:
        return _error(422, str(e))
    log.info("parsed deck slides=%d chars=%d", len(slides), sum(len(s.text) for s in slides))
    return {"slides": slides}


@app.post("/api/review")
def review(req: DeckRequest, request: Request):
    if (r := _limited(request, "ai", AI_LIMIT)):
        return r
    checks = numbers.check(req.slides)  # code first: these never depend on the AI
    try:
        rv, provider = ai.review(req.slides)
    except ai.StructuredError as e:
        log.warning("review_failed error=%s", e)
        return JSONResponse(status_code=502, content={"error": "The AI reviewer is busy. Your numbers check is below; try the review again in a minute.",
                                                      "numbers": checks})
    return {"review": rv, "score": ai.overall_score(rv), "numbers": checks, "provider": provider,
            "section_names": ai.SECTIONS}


@app.post("/api/question")
def question(req: QuestionRequest, request: Request):
    if (r := _limited(request, "ai", AI_LIMIT)):
        return r
    try:
        return {"question": ai.next_question(req.slides, req.asked, req.weak)}
    except ai.StructuredError as e:
        log.warning("question_failed error=%s", e)
        return _error(502, "The AI investor is busy. Try again in a minute.")


@app.post("/api/grade")
def grade(req: GradeRequest, request: Request):
    if (r := _limited(request, "ai", AI_LIMIT)):
        return r
    try:
        return {"grade": ai.grade(req.slides, req.question, req.answer)}
    except ai.StructuredError as e:
        log.warning("grade_failed error=%s", e)
        return _error(502, "The AI coach is busy. Your answer is kept; try again in a minute.")
