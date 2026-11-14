"""Turn an uploaded deck (PDF or PowerPoint) into plain text, one entry per slide."""

from __future__ import annotations

import io
import re

from pydantic import BaseModel

MAX_BYTES = 20 * 1024 * 1024
MAX_SLIDES = 40
MAX_CHARS_PER_SLIDE = 1500


class Slide(BaseModel):
    number: int
    text: str


class DeckError(Exception):
    pass


def _clean(s: str) -> str:
    s = s.replace(" ", " ").replace("\x00", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()[:MAX_CHARS_PER_SLIDE]


def from_pdf(data: bytes) -> list[Slide]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = reader.pages
    except Exception as e:  # pypdf raises many exception types for broken files
        raise DeckError("This PDF couldn't be opened. Try exporting it again.") from e
    if reader.is_encrypted:
        raise DeckError("This PDF is password-protected. Export an unprotected copy.")
    return [Slide(number=i + 1, text=_clean(p.extract_text() or "")) for i, p in enumerate(pages[:MAX_SLIDES])]


def from_pptx(data: bytes) -> list[Slide]:
    from pptx import Presentation

    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as e:
        raise DeckError("This PowerPoint file couldn't be opened. Try saving it again as .pptx.") from e
    slides = []
    for i, slide in enumerate(list(prs.slides)[:MAX_SLIDES]):
        parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                parts.append(f"(Speaker notes: {notes})")
        slides.append(Slide(number=i + 1, text=_clean("\n".join(parts))))
    return slides


def parse(filename: str, data: bytes) -> list[Slide]:
    if len(data) > MAX_BYTES:
        raise DeckError("That file is over 20 MB. Export a smaller copy.")
    name = filename.lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        slides = from_pdf(data)
    elif name.endswith(".pptx"):
        slides = from_pptx(data)
    elif name.endswith((".ppt", ".key")):
        raise DeckError("Save it as .pptx or export a PDF first. Older .ppt and Keynote files can't be read here.")
    else:
        raise DeckError("Upload a PDF or a PowerPoint (.pptx) file.")
    if not slides:
        raise DeckError("No slides found in that file.")
    if sum(len(s.text) for s in slides) < 40:
        raise DeckError("No readable text found. If the slides are images, export a PDF with real text, or paste the text instead.")
    return slides
