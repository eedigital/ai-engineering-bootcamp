"""Check the model's salary against the numbers actually written in the post.

Models sometimes misread long numbers ("¥11,000,000" came back as 10,000,000 in the held-out benchmark).
Plain code reads every salary range in the text. If one end of the model's range matches a range in the
post but the other end doesn't, the other end is taken from the post. Nothing is invented: a value is only
ever replaced by a number that is written in the post.
"""

from __future__ import annotations

import re

_UNITS = {"k": 1_000, "m": 1_000_000, "mn": 1_000_000, "million": 1_000_000, "lpa": 100_000, "lakh": 100_000,
          "lakhs": 100_000, "lac": 100_000, "cr": 10_000_000, "crore": 10_000_000}
_CUR = r"(?:US\$|USD|EUR|GBP|JPY|INR|CAD|AUD|CHF|CNY|KRW|IDR|BRL|MXN|SGD|[$€£¥₹₩])?"
_NUM = r"(\d{1,3}(?:[,.\s]\d{3})+|\d+(?:\.\d+)?)"
_UNIT = r"\s*(k|mn|m|million|lpa|lakhs?|lac|cr|crore)?\b"
_AMOUNT = _CUR + r"\s*" + _NUM + _UNIT
_RANGE = re.compile(_AMOUNT + r"\s*(?:-|–|—|to)\s*" + _AMOUNT, re.I)


def _value(num: str, unit: str | None) -> float:
    if re.fullmatch(r"\d{1,3}(?:[,.\s]\d{3})+", num):
        num = re.sub(r"[,.\s]", "", num)
    return float(num) * _UNITS.get((unit or "").lower(), 1)


def ranges(text: str) -> list[tuple[int, int]]:
    """Every salary-like range in the text, as whole numbers: '€70-85k' -> (70000, 85000)."""
    out = []
    for m in _RANGE.finditer(text):
        n1, u1, n2, u2 = m.group(1), m.group(2), m.group(3), m.group(4)
        unit = u2 or u1
        lo, hi = _value(n1, u1 or unit), _value(n2, u2 or unit)
        if lo <= hi:
            out.append((round(lo), round(hi)))
    return out


def fix_salary(salary_min: int | None, salary_max: int | None, text: str) -> tuple[int | None, int | None, bool]:
    """(min, max, corrected?). Only fills the end that disagrees, and only from a range written in the post."""
    if salary_min is None or salary_max is None:
        return salary_min, salary_max, False
    found = ranges(text)
    if (salary_min, salary_max) in found:
        return salary_min, salary_max, False
    for lo, hi in found:
        if lo == salary_min and hi != salary_max:
            return salary_min, hi, True
        if hi == salary_max and lo != salary_min:
            return lo, salary_max, True
    return salary_min, salary_max, False
