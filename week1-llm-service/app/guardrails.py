"""Input guardrails: run before any text reaches the model.

These are deliberately simple rules. Week 4's error analysis will tell you
which ones actually matter; add an LLM classifier then, not before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 8_000          # the most text sent to the model
MAX_INPUT_CHARS = 60_000   # longer than this is refused outright
MIN_CHARS = 20
# Lines worth keeping from the end of a long ad: pay and location usually sit near the bottom.
_KEEP_LINE = re.compile(r"salary|pay range|compensation|base pay|per (year|annum|hour)|[$€£¥₹₩]\s?\d|\b(USD|EUR|GBP|CAD|AUD|INR|JPY)\b|"
                        r"location|remote|hybrid|on-?site|in[- ]office", re.I)

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above)",
    r"you are now\b",
    r"system prompt",
    r"reveal (your|the) (instructions|prompt)",
    r"</?(system|assistant)>",
    r"act as (an? )?(dan|jailbroken)",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)")


@dataclass
class GuardResult:
    ok: bool
    text: str
    reason: str | None = None
    redactions: int = 0
    trimmed: bool = False


def trim_long(text: str) -> tuple[str, bool]:
    """Real ads run past 8,000 characters with benefits and legal text. Keep the start of the ad, plus any later
    line about pay or location, instead of refusing the ad (found by the real-ads benchmark: 5 of 12 were refused)."""
    if len(text) <= MAX_CHARS:
        return text, False
    head = text[: MAX_CHARS - 2_000]
    head = head[: head.rfind("\n")] if "\n" in head[-500:] else head
    kept, room = [], MAX_CHARS - len(head) - 10
    for line in text[len(head):].splitlines():
        line = line.strip()
        if line and _KEEP_LINE.search(line) and len(line) + 1 <= room:
            kept.append(line)
            room -= len(line) + 1
    return head + "\n[...]\n" + "\n".join(kept), True


# A range of amounts is a salary, not a phone: "90000-110000", "95.000 - 120.000", "95,000 - 120,000".
_AMOUNT = r"\d{1,3}(?:[.,\s]\d{3})+|\d+"
_NUMBER_RANGE_RE = re.compile(rf"^(?:{_AMOUNT})\s*-\s*(?:{_AMOUNT})$")


def _phone_or_keep(m: re.Match) -> str:
    s = m.group(0)
    digits = sum(c.isdigit() for c in s)
    if _NUMBER_RANGE_RE.match(s) or not 10 <= digits <= 15:
        return s
    return "[PHONE]"


def redact_pii(text: str) -> tuple[str, int]:
    text, n_email = _EMAIL_RE.subn("[EMAIL]", text)
    before = text.count("[PHONE]")
    text = _PHONE_RE.sub(_phone_or_keep, text)
    return text, n_email + text.count("[PHONE]") - before


def check_input(text: str) -> GuardResult:
    stripped = text.strip()
    if len(stripped) < MIN_CHARS:
        return GuardResult(False, text, f"input too short (min {MIN_CHARS} characters)")
    if len(stripped) > MAX_INPUT_CHARS:
        return GuardResult(False, text, f"input too long (max {MAX_INPUT_CHARS:,} characters)")
    if _INJECTION_RE.search(stripped):
        return GuardResult(False, text, "input looks like a prompt-injection attempt")
    short, trimmed = trim_long(stripped)
    clean, n = redact_pii(short)
    return GuardResult(True, clean, redactions=n, trimmed=trimmed)
