"""The full Harmonized System (HS 2022): every 6-digit code, with search by plain words.

Data: UN Comtrade's HS 2022 classification, via datahub.io (ODC Public Domain Dedication and Licence).
The 6-digit level is shared by every country; countries add their own digits after it.

Search turns plain words into ranked codes. HS descriptions use trade wording ("Coffee; not roasted"),
so a few everyday words are mapped to it ("laptop" -> "data processing"), and a word that appears after
"not" or "other than" counts against a code rather than for it.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "hs2022.csv"
EDITION = "HS 2022"

STOP = {"a", "an", "the", "of", "and", "or", "for", "with", "in", "on", "to", "from", "our", "my", "we", "per", "kg",
        "organic", "premium", "quality", "grade", "new", "product", "products", "goods", "made", "export", "exports"}
# everyday words -> the words HS descriptions use
SYNONYMS = {
    "laptop": "portable data processing", "computer": "data processing", "phone": "telephone", "smartphone": "telephone smartphone",
    "mobile": "telephone", "solar": "photovoltaic", "shoe": "footwear", "sneaker": "footwear", "boot": "footwear",
    "sandal": "footwear", "beef": "bovine meat", "pork": "swine meat", "chicken": "fowl meat", "lamb": "sheep meat",
    "battery": "accumulator", "tv": "television", "television": "television reception", "sunglass": "spectacle sunglass",
    "jean": "trouser denim", "car": "motor car vehicle", "truck": "motor vehicle goods transport", "green": "unroasted",
    "salmon": "salmon", "steel": "iron steel", "pipe": "tube pipe", "chair": "seat", "sofa": "seat", "bike": "bicycle",
    "fridge": "refrigerator", "perfume": "perfume", "makeup": "make up", "lipstick": "lip make up", "soap": "soap",
    "juice": "juice", "beer": "beer malt", "whisky": "whiskies", "vodka": "vodka", "tequila": "spirituous beverage", "nut": "nut",
    "shrimp": "shrimp prawn", "prawn": "shrimp prawn", "hoodie": "jersey pullover", "sweater": "jersey pullover",
    "wallet": "pocket handbag", "purse": "pocket handbag", "backpack": "case container textile", "suitcase": "trunk suit case",
    "rug": "carpet", "mug": "tableware", "plate": "tableware", "toy": "toy", "doll": "doll", "pen": "pen",
}


# qualities that split one product into several codes; a code naming one the buyer didn't ask for ranks lower
_QUALITIES = {"decaffeinated", "roasted", "sparkling", "frozen", "chilled", "dried", "salted", "smoked", "crude", "refined",
              "sport", "waterproof", "synthetic", "artificial", "knitted", "crocheted", "used", "seed", "breeding"}


def _stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ches", "shes", "xes")) or len(w) > 5 and w.endswith("oes"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z]+", text.lower().replace("t-shirt", "tshirt"))]


@lru_cache(maxsize=1)
def table() -> dict[str, str]:
    with DATA.open(encoding="utf-8") as f:
        # chapters 98 and 99 are national or statistical codes, not part of the shared HS
        return {r["code"]: r["description"] for r in csv.DictReader(f) if not r["code"].startswith(("98", "99"))}


@lru_cache(maxsize=1)
def _vocab() -> set[str]:
    return {w for d in table().values() for w in _words(d)}


@lru_cache(maxsize=1)
def _index() -> list[tuple[str, set[str], set[str], set[str], set[str], int]]:
    """For each 6-digit code: its words, its heading's words, its chapter's words, negated words, description length."""
    t = table()
    out = []
    for code, desc in t.items():
        if len(code) != 6:
            continue
        neg = set()
        for m in re.finditer(r"\b(?:not|other than|excluding|except|neither|nor|without)\s+((?:[a-z\-]+[ ,]*){1,3})", desc.lower()):
            neg.update(_words(m.group(1)))
        sub = set(_words(desc)) | {"un" + w for w in neg}  # "not roasted" also reads as "unroasted"
        out.append((code, sub, set(_words(t.get(code[:4], ""))), set(_words(t.get(code[:2], ""))), neg, len(desc)))
    return out


def valid(code: str | None) -> bool:
    c = re.sub(r"\D", "", code or "")
    return len(c) in (2, 4, 6) and c in table() or (len(c) > 6 and c[:6] in table())


def describe(code: str | None) -> str | None:
    """The official description for a code (6 digits, or the first 6 of a longer national code)."""
    c = re.sub(r"\D", "", code or "")
    t = table()
    return t.get(c) or (t.get(c[:6]) if len(c) > 6 else None)


def search(query: str, limit: int = 6) -> list[dict]:
    """6-digit codes ranked for plain words, e.g. 'green coffee' -> 090111 first."""
    terms: list[str] = []
    for w in _words(query):
        if w in STOP or len(w) < 2:
            continue
        if w in SYNONYMS:
            keep = w in _vocab() and w not in ("shoe", "sneaker", "boot", "green", "laptop")
            terms += ([w] if keep else []) + _words(SYNONYMS[w])
        else:
            terms.append(w)
    terms = list(dict.fromkeys(t for t in terms if t not in STOP))
    if not terms:
        return []
    scored = []
    for code, sub, head, chap, neg, length in _index():
        score = 0.0
        hit = 0
        for t in terms:
            if t in neg:
                score -= 2.5
            elif t in sub:
                score += 3
                hit += 1
            elif t in head:
                score += 2
                hit += 1
            elif t in chap:
                score += 0.75
                hit += 1
        if hit == 0:
            continue
        score += 2 if hit == len(terms) else 0
        # a code that adds a quality the query didn't ask for ("decaffeinated") ranks below one that doesn't
        extra = {w for w in sub - neg - set(terms) if not w.startswith("un") and w in _QUALITIES}
        score -= 0.5 * len(extra)
        score -= length / 400  # prefer the plainer description when scores tie
        scored.append((score, code))
    scored.sort(key=lambda s: -s[0])
    t = table()
    return [{"code": c, "description": t[c], "heading": t.get(c[:4], ""), "score": round(s, 2)} for s, c in scored[:limit] if s > 0]


# --- what a product needs, from its HS chapter, for products outside our hand-made list ------------------

EUDR_PREFIXES = ("0102", "0201", "0202", "0206", "4101", "4104", "4107", "0901", "1801", "1802", "1803", "1804", "1805", "1806",
                 "1201", "1208", "1507", "2304", "1511", "1513", "3823", "4001", "4005", "4011", "4012", "4013", "4015", "4016",
                 "44", "47", "48", "49", "940330", "940340", "940350", "940360", "940391", "9406")
EUDR_NAMES = {"01": "cattle", "02": "cattle", "41": "cattle", "09": "coffee", "18": "cocoa", "12": "soy", "15": "palm",
              "23": "soy", "38": "palm", "40": "rubber", "44": "wood", "47": "wood", "48": "wood", "49": "wood", "94": "wood"}


def needs(code: str) -> dict:
    """plant / animal / food / EUDR flags from the HS chapter."""
    c = re.sub(r"\D", "", code or "")[:6]
    ch = int(c[:2]) if c[:2].isdigit() else 0
    eudr = EUDR_NAMES.get(c[:2]) if any(c.startswith(p) for p in EUDR_PREFIXES) else None
    return {"plant": 6 <= ch <= 14, "animal": 1 <= ch <= 5 or (ch == 16 and c[:4] in ("1601", "1602", "1603", "1604", "1605")),
            "food": 1 <= ch <= 24, "eudr": eudr}
