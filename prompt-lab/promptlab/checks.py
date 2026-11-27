"""Score an answer against a case's expectations, in code.

The model never grades itself here: every pass or fail comes from a rule a person can read, with a reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from llm import parse_json

from .models import Expect, Value


@dataclass
class Score:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()  # accents are kept on purpose: "Gracia" is not "Gràcia"


def _show(v: object) -> str:
    return json.dumps(v, ensure_ascii=False)


def _same(got: object, want: Value) -> bool:
    if isinstance(want, bool) or isinstance(got, bool):
        return got is want  # "false" (a string) or 0 is not false: the schema is part of the test
    if isinstance(want, (int, float)):
        return isinstance(got, (int, float)) and float(got) == float(want)
    return isinstance(got, str) and _norm(got) == _norm(want)


def score(answer: str, expect: Expect) -> Score:
    text = answer.strip()
    reasons: list[str] = []

    if expect.fields is not None:
        try:
            data = parse_json(text)
        except (json.JSONDecodeError, ValueError):
            data = None
        if not isinstance(data, dict):
            reasons.append("Not a valid JSON object")
        else:
            for key, want in expect.fields.items():
                if key not in data:
                    reasons.append(f'Missing "{key}"')
                elif not _same(data[key], want):
                    reasons.append(f"{key}: expected {_show(want)}, got {_show(data[key])}")
            extra = sorted(set(data) - set(expect.fields))
            if extra:
                reasons.append("Extra keys: " + ", ".join(extra))

    if expect.equals is not None and _norm(text) != _norm(expect.equals):
        reasons.append(f"Expected {_show(expect.equals)}")

    if expect.max_chars is not None and len(text) > expect.max_chars:
        reasons.append(f"{len(text)} characters, limit {expect.max_chars}")

    folded = _norm(text)
    for s in expect.contains:
        if _norm(s) not in folded:
            reasons.append(f'Missing "{s}"')
    for s in expect.not_contains:
        if _norm(s) in folded:
            reasons.append(f'Contains "{s}"')

    return Score(passed=not reasons, reasons=reasons)


def describe(expect: Expect) -> str:
    """One line a person can read, for the page and for the improver."""
    parts: list[str] = []
    if expect.fields is not None:
        parts.append("JSON " + ", ".join(f"{k} = {_show(v)}" for k, v in expect.fields.items()))
    if expect.equals is not None:
        parts.append(f"exactly {_show(expect.equals)}")
    if expect.max_chars is not None:
        parts.append(f"at most {expect.max_chars} characters")
    if expect.contains:
        parts.append("includes " + ", ".join(_show(s) for s in expect.contains))
    if expect.not_contains:
        parts.append("never " + ", ".join(_show(s) for s in expect.not_contains))
    return "; ".join(parts) or "any answer"
