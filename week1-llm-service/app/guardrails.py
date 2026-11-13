"""Input guardrails: run before any text reaches the model.

These are deliberately simple rules. Week 4's error analysis will tell you
which ones actually matter; add an LLM classifier then, not before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 8_000
MIN_CHARS = 20

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


_NUMBER_RANGE_RE = re.compile(r"^\d+\s*-\s*\d+$")  # "90000-110000" is a salary, not a phone


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
    if len(stripped) > MAX_CHARS:
        return GuardResult(False, text, f"input too long (max {MAX_CHARS} characters)")
    if _INJECTION_RE.search(stripped):
        return GuardResult(False, text, "input looks like a prompt-injection attempt")
    clean, n = redact_pii(stripped)
    return GuardResult(True, clean, redactions=n)
