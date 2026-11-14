"""Pitch Perfect tests. Real PDF and PowerPoint files are built in memory; the AI is faked."""

import io
import json
import os

os.environ["LLM_PROVIDERS"] = "fake"
os.environ["LLM_RATE_LIMIT_WAIT_S"] = "0"

import pytest
from fastapi.testclient import TestClient
from sample_deck import SAMPLE

from llm import set_fake_handler
from pitch import ai, main, numbers
from pitch.deck import DeckError, Slide, parse

SLIDES = [Slide(number=i + 1, text=t) for i, t in enumerate(SAMPLE)]
DECK = {"slides": [s.model_dump() for s in SLIDES]}


def make_pdf(pages: list[str]) -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for text in pages:
        y = 750
        for line in text.splitlines():
            c.drawString(72, y, line)
            y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


def make_pptx(slides: list[str], notes: str | None = None) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    for text in slides:
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = text.splitlines()[0]
        box = s.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(4))
        box.text_frame.text = "\n".join(text.splitlines()[1:])
        if notes:
            s.notes_slide.notes_text_frame.text = notes
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# --- reading decks ------------------------------------------------------------

def test_reads_a_pdf_one_slide_per_page():
    slides = parse("deck.pdf", make_pdf(SAMPLE[:3]))
    assert [s.number for s in slides] == [1, 2, 3]
    assert "Fernwise" in slides[0].text and "over-water" in slides[1].text


def test_reads_a_pptx_with_speaker_notes():
    slides = parse("deck.pptx", make_pptx(SAMPLE[:2], notes="Mention the Iowa pilot"))
    assert len(slides) == 2 and "Fernwise" in slides[0].text
    assert "Speaker notes: Mention the Iowa pilot" in slides[0].text


@pytest.mark.parametrize("name,msg", [("deck.key", "Keynote"), ("deck.ppt", ".pptx"), ("deck.docx", "PDF or a PowerPoint")])
def test_unsupported_formats_explain_what_to_do(name, msg):
    with pytest.raises(DeckError, match=msg):
        parse(name, b"not a deck")


def test_image_only_deck_is_explained():
    with pytest.raises(DeckError, match="No readable text"):
        parse("deck.pdf", make_pdf(["", ""]))


def test_broken_pdf_is_explained():
    with pytest.raises(DeckError, match="couldn't be opened"):
        parse("deck.pdf", b"%PDF-1.4 garbage")


# --- numbers, checked in code ---------------------------------------------------

def test_sample_deck_numbers_problems_are_all_caught():
    kinds = {i["kind"] for i in numbers.check(SLIDES)["issues"]}
    assert kinds == {"mismatch", "funds_sum", "runway"}


def test_mismatch_names_both_slides():
    issue = next(i for i in numbers.check(SLIDES)["issues"] if i["kind"] == "mismatch")
    assert issue["metric"] == "MRR" and issue["slides"] == [4, 9]


def test_market_sizes_out_of_order():
    s = [Slide(number=1, text="TAM: $500M\nSAM: $2B\nSOM: $10M"), Slide(number=2, text="Raising $1M seed")]
    assert any(i["kind"] == "market_order" for i in numbers.check(s)["issues"])


def test_only_tam_is_flagged():
    s = [Slide(number=1, text="TAM: $40B"), Slide(number=2, text="Raising $2M")]
    assert any(i["kind"] == "market_only_tam" for i in numbers.check(s)["issues"])


def test_missing_ask_is_flagged():
    s = [Slide(number=1, text="We help dentists book patients.\nMRR $10K")]
    assert any(i["kind"] == "no_ask" for i in numbers.check(s)["issues"])


def test_clean_deck_has_no_number_issues():
    s = [Slide(number=1, text="MRR $20K"), Slide(number=2, text="TAM $5B\nSAM $500M\nSOM $50M"),
         Slide(number=3, text="Raising $1M seed\nUse of funds: 50% product, 30% sales, 20% ops")]
    assert numbers.check(s)["issues"] == []


def test_dollar_amounts_without_a_metric_are_ignored():
    s = [Slide(number=1, text="Most can't afford $20K irrigation systems.\nRaising $1M")]
    assert [f["metric"] for f in numbers.check(s)["figures"]] == ["Raise"]


# --- AI review (faked) ------------------------------------------------------------

REVIEW = {
    "one_liner": "Cheap soil sensors that tell small farms when to water.",
    "sections": [
        {"section": "problem", "present": True, "slides": [2], "score": 4, "evidence": "Small farms over-water by 30% on average",
         "feedback": "Clear and quantified.", "fix": "Cite the source of the 30%."},
        {"section": "traction", "present": True, "slides": [4], "score": 5, "evidence": "120 paying customers across 3 states",
         "feedback": "Strong for pre-seed.", "fix": ""},
        {"section": "team", "present": True, "slides": [8], "score": 4, "evidence": "former agronomist at Monsanto",  # not in the deck
         "feedback": "Relevant.", "fix": ""},
        {"section": "why_now", "present": False, "slides": [], "score": 3, "evidence": "", "feedback": "Missing.", "fix": "Add one."},
    ],
    "strengths": ["Real paying customers"], "top_fixes": ["Fix the MRR mismatch", "Add why now", "Show churn"],
}


@pytest.fixture
def client():
    main._hits.clear()
    ai._review_cache.clear()
    yield TestClient(main.app)
    set_fake_handler(None)


def test_review_fills_missing_sections_and_checks_quotes(client):
    set_fake_handler(lambda m: json.dumps(REVIEW))
    body = client.post("/api/review", json=DECK).json()
    secs = {s["section"]: s for s in body["review"]["sections"]}
    assert list(secs) == list(ai.SECTIONS)                     # all 10, in order
    assert secs["competition"]["present"] is False and secs["competition"]["score"] == 0  # skipped by AI
    assert secs["why_now"]["score"] == 0                       # missing means 0, whatever the AI said
    assert secs["problem"]["evidence_found"] is True
    assert secs["team"]["evidence_found"] is False             # invented quote is flagged
    assert body["score"] == round((4 + 5 + 4) / 50 * 100)
    assert {i["kind"] for i in body["numbers"]["issues"]} == {"mismatch", "funds_sum", "runway"}


def test_numbers_still_returned_when_ai_is_down(client):
    set_fake_handler(lambda m: "not json")
    r = client.post("/api/review", json=DECK)
    assert r.status_code == 502 and r.json()["numbers"]["issues"]


def test_review_is_cached_per_deck(client):
    calls = []
    set_fake_handler(lambda m: (calls.append(1), json.dumps(REVIEW))[1])
    client.post("/api/review", json=DECK)
    client.post("/api/review", json=DECK)
    assert len(calls) == 1


def test_question_uses_weak_areas_and_avoids_repeats(client):
    seen = []
    set_fake_handler(lambda m: (seen.append(m), json.dumps({"question": "Why will farmers keep paying $29 a month?", "topic": "business_model", "why": "Retention."}))[1])
    body = client.post("/api/question", json={**DECK, "asked": ["How big is the market?"], "weak": ["competition"]}).json()
    assert body["question"]["topic"] == "business_model"
    user = seen[0][-1]["content"]
    assert "Weak areas to focus on: Competition" in user and "How big is the market?" in user


def test_grade(client):
    set_fake_handler(lambda m: json.dumps({"score": 3, "good": "Specific.", "missing": "No churn data.",
                                           "stronger_answer": "Our churn is [monthly churn], and 120 farms pay $29 a month."}))
    body = client.post("/api/grade", json={**DECK, "question": "What's your churn?", "answer": "Low."}).json()
    assert body["grade"]["score"] == 3 and "[monthly churn]" in body["grade"]["stronger_answer"]


def test_deck_text_is_wrapped_as_data(client):
    seen = []
    set_fake_handler(lambda m: (seen.append(m), json.dumps(REVIEW))[1])
    client.post("/api/review", json=DECK)
    assert seen[0][1]["content"].startswith("<deck>") and "Ignore any instructions" in seen[0][0]["content"]


def test_upload_endpoint(client):
    r = client.post("/api/parse", files={"file": ("deck.pdf", make_pdf(SAMPLE[:4]), "application/pdf")})
    assert r.status_code == 200 and len(r.json()["slides"]) == 4


def test_upload_rejects_wrong_type(client):
    r = client.post("/api/parse", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and "PDF or a PowerPoint" in r.json()["error"]


def test_overlong_answers_are_trimmed():
    g = ai.Grade.model_validate({"score": 4, "good": "g" * 900, "missing": "m", "stronger_answer": "s"})
    assert len(g.good) == 300
