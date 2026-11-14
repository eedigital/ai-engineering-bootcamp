"""A plain-code reader for a buyer's message. No AI, so it always works, even when the AI is busy.

It finds what's easy to find reliably: amounts, currencies, quantities, containers, countries,
ports, delivery terms and payment terms. The AI reader (ai.py) adds what needs judgement.
"""

from __future__ import annotations

import re

COUNTRIES = [
    "Argentina", "Australia", "Austria", "Bangladesh", "Belgium", "Bolivia", "Brazil", "Bulgaria", "Cambodia", "Cameroon",
    "Canada", "Chile", "China", "Colombia", "Costa Rica", "Côte d'Ivoire", "Ivory Coast", "Croatia", "Czechia", "Czech Republic",
    "Denmark", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Estonia", "Ethiopia", "Finland", "France", "Germany",
    "Ghana", "Greece", "Guatemala", "Honduras", "Hong Kong", "Hungary", "India", "Indonesia", "Ireland", "Israel", "Italy",
    "Jamaica", "Japan", "Jordan", "Kenya", "Latvia", "Lithuania", "Luxembourg", "Malaysia", "Malta", "Mexico", "Morocco",
    "Netherlands", "New Zealand", "Nicaragua", "Nigeria", "Norway", "Pakistan", "Panama", "Paraguay", "Peru", "Philippines",
    "Poland", "Portugal", "Romania", "Rwanda", "Saudi Arabia", "Senegal", "Singapore", "Slovakia", "Slovenia", "South Africa",
    "South Korea", "Korea", "Spain", "Sri Lanka", "Sweden", "Switzerland", "Taiwan", "Tanzania", "Thailand", "Tunisia", "Turkey",
    "Türkiye", "Uganda", "Ukraine", "United Arab Emirates", "UAE", "United Kingdom", "UK", "United States", "USA", "US",
    "Uruguay", "Vietnam", "Viet Nam", "Zambia",
]
ALIASES = {"Ivory Coast": "Côte d'Ivoire", "Czech Republic": "Czechia", "Korea": "South Korea", "Türkiye": "Turkey",
           "UAE": "United Arab Emirates", "UK": "United Kingdom", "USA": "United States", "US": "United States", "Viet Nam": "Vietnam",
           "Holland": "Netherlands"}

# Ports and trade cities, with their country. The place name is kept for the named place.
PLACES = {
    "Hamburg": "Germany", "Bremen": "Germany", "Bremerhaven": "Germany", "Rotterdam": "Netherlands", "Amsterdam": "Netherlands",
    "Antwerp": "Belgium", "Le Havre": "France", "Marseille": "France", "Valencia": "Spain", "Barcelona": "Spain",
    "Algeciras": "Spain", "Genoa": "Italy", "Trieste": "Italy", "Felixstowe": "United Kingdom", "Southampton": "United Kingdom",
    "London": "United Kingdom", "Gdansk": "Poland", "Piraeus": "Greece", "Gothenburg": "Sweden", "Copenhagen": "Denmark",
    "Cartagena": "Colombia", "Buenaventura": "Colombia", "Santa Marta": "Colombia", "Barranquilla": "Colombia", "Bogota": "Colombia",
    "Medellin": "Colombia", "Santos": "Brazil", "Callao": "Peru", "Guayaquil": "Ecuador", "Valparaiso": "Chile",
    "San Antonio": "Chile", "Manzanillo": "Mexico", "Veracruz": "Mexico", "Puerto Cortes": "Honduras", "Mombasa": "Kenya",
    "Dar es Salaam": "Tanzania", "Tema": "Ghana", "Abidjan": "Côte d'Ivoire", "Lagos": "Nigeria", "Durban": "South Africa",
    "Djibouti": "Ethiopia", "Shanghai": "China", "Shenzhen": "China", "Ningbo": "China", "Hong Kong": "Hong Kong",
    "Singapore": "Singapore", "Busan": "South Korea", "Tokyo": "Japan", "Yokohama": "Japan", "Ho Chi Minh City": "Vietnam",
    "Haiphong": "Vietnam", "Jakarta": "Indonesia", "Chittagong": "Bangladesh", "Mumbai": "India", "Nhava Sheva": "India",
    "Chennai": "India", "Colombo": "Sri Lanka", "Dubai": "United Arab Emirates", "Jebel Ali": "United Arab Emirates",
    "New York": "United States", "Los Angeles": "United States", "Long Beach": "United States", "Miami": "United States",
    "Houston": "United States", "Savannah": "United States", "Vancouver": "Canada", "Montreal": "Canada", "Toronto": "Canada",
    "Sydney": "Australia", "Melbourne": "Australia",
}

INCOTERMS = ("EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP")
CURRENCY_WORDS = {"usd": "USD", "us$": "USD", "$": "USD", "dollars": "USD", "eur": "EUR", "€": "EUR", "euro": "EUR", "euros": "EUR",
                  "gbp": "GBP", "£": "GBP", "pounds": "GBP", "jpy": "JPY", "¥": "JPY", "cny": "CNY", "chf": "CHF", "cad": "CAD",
                  "aud": "AUD", "inr": "INR", "brl": "BRL", "cop": "COP", "mxn": "MXN", "aed": "AED"}
NUMBER_WORDS = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "twelve": 12, "twenty": 20}
COMPANY = r"(?:GmbH|AG|KG|Ltd\.?|Limited|LLC|Inc\.?|Corp\.?|B\.?V\.?|N\.?V\.?|S\.?A\.?S?|S\.?r\.?l\.?|S\.?L\.?|Pty|Oy|AB|A/S|SpA|Co\.)"


def _num(s: str) -> float | None:
    """'210,000' -> 210000; '210.000' (European) -> 210000; '1.5' -> 1.5."""
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _scale(value: float, word: str | None) -> float:
    w = (word or "").lower()
    return value * (1_000_000 if w in ("m", "mn", "million") else 1_000 if w in ("k", "thousand") else 1)


def money(text: str) -> tuple[float | None, str | None, float | None, str | None]:
    """(total, currency, unit price, unit) from the text. The largest amount not written 'per X' is taken as the total."""
    cur = r"(US\$|USD|EUR|GBP|JPY|CNY|CHF|CAD|AUD|INR|BRL|COP|MXN|AED|\$|€|£|¥)"
    amt = r"(\d[\d,\.]*)\s*(million|thousand|mn|m|k)?\b"
    found: list[tuple[float, str, str | None]] = []  # value, currency, per-unit
    for m in re.finditer(cur + r"\s?" + amt + r"(\s*(?:per|/)\s*(kg|kilo|lb|tonne|ton|mt|bag|box|unit|piece|pc|carton|bottle|case))?", text, re.I):
        v = _num(m.group(2))
        if v is not None:
            found.append((_scale(v, m.group(3)), CURRENCY_WORDS.get(m.group(1).lower(), m.group(1).upper()), m.group(5)))
    for m in re.finditer(amt + r"\s*(USD|EUR|GBP|euros?|dollars|pounds|JPY|CNY|CHF|CAD|AUD)(\s*(?:per|/)\s*(kg|kilo|lb|tonne|ton|mt|bag|box|unit|piece|carton|bottle|case))?", text, re.I):
        v = _num(m.group(1))
        if v is not None:
            found.append((_scale(v, m.group(2)), CURRENCY_WORDS.get(m.group(3).lower(), m.group(3).upper()), m.group(5)))
    totals = [f for f in found if not f[2]]
    units = [f for f in found if f[2]]
    total = max(totals, key=lambda f: f[0]) if totals else None
    unit = units[0] if units else None
    currency = (total or unit or (None, None, None))[1]
    return (total[0] if total else None, currency, unit[0] if unit else None, _unit_name(unit[2]) if unit else None)


def _unit_name(u: str | None) -> str | None:
    if not u:
        return None
    u = u.lower()
    return {"kilo": "kg", "ton": "tonne", "mt": "tonne", "pc": "piece"}.get(u, u)


def quantity(text: str) -> tuple[float | None, str | None]:
    """The goods quantity, in kg where possible."""
    m = re.search(r"(\d[\d,\.]*)\s*(kg|kgs|kilos?|kilograms?)\b", text, re.I)
    if m and (v := _num(m.group(1))):
        return v, "kg"
    m = re.search(r"(\d[\d,\.]*)\s*(metric tons?|metric tonnes?|tonnes?|tons?|mt)\b", text, re.I)
    if m and (v := _num(m.group(1))):
        return v * 1000, "kg"
    m = re.search(r"(\d[\d,\.]*)\s*(bags|boxes|cartons|units|pieces|pcs|bottles|cases|pallets|sacks|bales|drums)\b", text, re.I)
    if m and (v := _num(m.group(1))):
        return v, m.group(2).lower().replace("pcs", "pieces")
    return None, None


def containers(text: str) -> tuple[int | None, str | None]:
    words = "|".join(NUMBER_WORDS)
    m = re.search(rf"\b(\d+|{words})\s*(?:x\s*)?(?:(20|40)\s*(?:'|’|ft|foot|feet|-foot)?\s*(?:hc|high cube)?\s*)?(?:full\s+)?(?:containers?|fcls?|boxes of 20|ctrs?)\b",
                  text, re.I)
    if not m:
        m2 = re.search(r"\b(20|40)\s*(?:'|’|ft|foot|-foot)\s*(?:hc\s*)?container\b", text, re.I)
        return (1, m2.group(1) + "ft") if m2 else (None, None)
    n = m.group(1).lower()
    count = int(n) if n.isdigit() else NUMBER_WORDS.get(n)
    return count, (m.group(2) + "ft" if m.group(2) else None)


def _find_places(text: str) -> list[tuple[int, str, str | None]]:
    """(position, country, place) for every country or known port in the text."""
    out: list[tuple[int, str, str | None]] = []
    for c in COUNTRIES + ["Holland"]:
        flags = 0 if c in ("US", "UK", "UAE") else re.I
        for m in re.finditer(rf"(?<![\w]){re.escape(c)}(?![\w])", text, flags):
            out.append((m.start(), ALIASES.get(c, c), None))
    for place, country in PLACES.items():
        for m in re.finditer(rf"(?<![\w]){re.escape(place)}(?![\w])", text, re.I):
            out.append((m.start(), country, place))
    return sorted(out)


ORIGIN_CUE = r"(from|out of|grown in|produced in|made in|based in|farm in|farms in|exporter in|supplier in|ship(ping)? from|loading (at|in)|port of loading)\s+(the\s+)?(port of\s+)?$"
DEST_CUE = r"(to|into|buyer in|buyers in|customer in|importer in|roaster in|client in|deliver(ed|y)? (to|in)|port of discharge|destination|arrive (in|at)|discharge (in|at))\s+(the\s+)?(port of\s+)?$"


def route(text: str, home_country: str | None = None) -> dict:
    """Work out origin and destination from cue words: 'from X' and 'we grow in X' point at the origin,
    'to X' and 'buyer in X' at the destination. A bare 'in X' counts as the origin when the sentence is about
    the seller ('I', 'we'), otherwise the destination."""
    found = _find_places(text)
    scores: dict[str, list[float]] = {}  # country -> [origin score, destination score]
    places: dict[tuple[str, str], str] = {}  # (country, role) -> place name
    for i, (pos, country, place) in enumerate(found):
        before = text[max(0, pos - 30):pos].lower()
        sentence = re.split(r"[.!?\n]", text[:pos])[-1].strip().lower()
        # "Hamburg, Germany": the country inherits the cue of the place right before it
        if i and found[i - 1][1] == country and pos - found[i - 1][0] < 30:
            before = text[max(0, found[i - 1][0] - 30):found[i - 1][0]].lower()
        o = d = 0.0
        if re.search(ORIGIN_CUE, before):
            o = 2
        elif re.search(DEST_CUE, before):
            d = 2
        elif re.search(r"\bin\s+(the\s+)?$", before):
            if re.match(r"(i|we|i'm|we're|my|our)\b", sentence):
                o = 1
            else:
                d = 1
        s_ = scores.setdefault(country, [0.0, 0.0])
        s_[0] += o
        s_[1] += d
        if place:
            if o and (country, "o") not in places:
                places[(country, "o")] = place
            if d and (country, "d") not in places:
                places[(country, "d")] = place
            places.setdefault((country, "any"), place)
    countries = list(scores)
    net_d = {c: scores[c][1] - scores[c][0] for c in countries}
    origin = home_country
    dest_pool = [c for c in countries if c != origin and net_d[c] > 0]
    dest = max(dest_pool, key=lambda c: net_d[c]) if dest_pool else None
    if not origin:
        rest = [c for c in countries if c != dest]
        origin = max(rest, key=lambda c: -net_d[c]) if rest else None
    if not dest:
        rest = [c for c in countries if c != origin]
        dest = max(rest, key=lambda c: net_d[c]) if rest else None
    return {"origin_country": origin, "destination_country": dest,
            "origin_place": places.get((origin, "o")) or places.get((origin, "any")) if origin else None,
            "destination_place": places.get((dest, "d")) or places.get((dest, "any")) if dest else None}


def incoterm(text: str) -> str | None:
    m = re.search(rf"\b({'|'.join(INCOTERMS)})\b(\s+[A-Z][\w\-]+(?:\s+[A-Z][\w\-]+)?)?", text)
    return (m.group(1) + (m.group(2) or "")).strip() if m else None


def payment(text: str) -> dict:
    t = text.lower()
    days = re.search(r"(\d{2,3})\s*days?\s*(after|from|following|net|of)?\s*(delivery|arrival|invoice|bill of lading|b/l|bl|shipment|receipt)?", t)
    out: dict = {"mentioned": None, "credit_days": None, "kind": None}
    if re.search(r"letter of credit|\bl/c\b|\blc\b|documentary credit", t):
        out["kind"] = "lc"
    elif re.search(r"documents against payment|\bd/p\b|\bcad\b|cash against documents", t):
        out["kind"] = "collection"
    elif re.search(r"\badvance\b|prepay|pre-pay|upfront|up front|deposit", t):
        out["kind"] = "advance"
    if days and (days.group(2) or days.group(3) or "pay" in t[max(0, days.start() - 40):days.start()]):
        out["credit_days"] = int(days.group(1))
        out["kind"] = out["kind"] or "open"
    m = re.search(r"[^.\n]*\b(pay|payment|paid)\b[^.\n]*", text, re.I)
    out["mentioned"] = m.group(0).strip()[:200] if m else None
    return out


def relationship(text: str) -> str | None:
    t = text.lower()
    if re.search(r"first (order|export|shipment|time|deal)|new (buyer|customer|client)|never (sold|worked)|haven't (sold|worked)", t):
        return "new"
    if re.search(r"(regular|long[- ]standing|repeat) (buyer|customer|client)|for (many|several|\d+) years|again this year|as usual", t):
        return "established"
    if re.search(r"(second|third|another) (order|shipment)|sold to them before|worked with them before", t):
        return "some"
    return None


def mode(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bby air\b|air ?freight|air waybill|\bairport\b|\bfly\b", t):
        return "air"
    if re.search(r"\bbulk\b|break ?bulk|\bvessel hold", t):
        return "sea_bulk"
    if re.search(r"container|\bfcl\b|\blcl\b|by sea|ocean|shipping line|\bvessel\b|\bship\b", t):
        return "sea_container"
    if re.search(r"\btruck|by road|lorry", t):
        return "road"
    if re.search(r"\brail\b|by train", t):
        return "rail"
    return None


def buyer_name(text: str) -> str | None:
    m = re.search(rf"\b((?:[A-Z][\w&'\-]*\s){{0,4}}[A-Z][\w&'\-]*\s{COMPANY})(?![\w])", text)
    return m.group(1).strip() if m else None


def buyer_address(text: str, name: str | None) -> str | None:
    """The rest of the line after the buyer's company name, when it looks like an address ('Am Sandtorkai 12, 20457 Hamburg')."""
    if not name:
        return None
    m = re.search(re.escape(name) + r"\s*,\s*([^\n]{8,160})", text)
    if m and re.search(r"\d", m.group(1)):
        return m.group(1).strip().rstrip(".")
    return None


MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"


def ship_window(text: str) -> str | None:
    m = re.search(rf"(?:ship(?:ment|ping)?|deliver(?:y|ed)?|load(?:ing)?|dispatch)\b[^.\n]{{0,25}}?\b((?:early |mid |mid-|late |end of )?(?:{MONTHS})(?:\s*(?:-|to|/)\s*(?:{MONTHS}))?(?:\s+20\d\d)?|Q[1-4]\s*20\d\d|week\s*\d+)",
                  text, re.I)
    return m.group(1).strip() if m else None


RISK_PATTERNS = [
    (r"(new|changed|updated|different) bank (details|account)", "Changed bank details", "high",
     "A request to pay into new bank details is a common fraud sign. Confirm by phone with a number you already have."),
    (r"pay(ment)? (only )?(after|once|when) (we|they|the goods are) (sell|sold|resell)|consignment", "Payment only after resale", "high",
     "You'd carry the buyer's sales risk and wait an unknown time to be paid."),
    (r"\bddp\b", "The buyer wants DDP", "medium",
     "Under DDP you pay import duties and taxes in the buyer's country and may need to register there."),
    (r"(urgent|asap|immediately|right away)", "Pressure to act fast", "low",
     "Urgency is a common pressure tactic. Take the time to check the buyer."),
    (r"penalt(y|ies)|liquidated damages", "Penalties", "medium", "Check what triggers the penalty and cap it."),
    (r"free samples?", "Free samples before payment", "low", "Agree who pays for samples and shipping before sending them."),
    (r"overpa(y|id|yment)|refund the (difference|balance)", "Overpayment and refund", "high",
     "Overpaying and asking for a refund is a known fraud pattern."),
]


def risks(text: str, credit_days: int | None, rel: str | None) -> list[dict]:
    out = []
    for pat, flag, sev, why in RISK_PATTERNS:
        m = re.search(r"[^.\n]*" + pat + r"[^.\n]*", text, re.I)
        if m:
            out.append({"flag": flag, "quote": m.group(0).strip()[:300], "why": why, "severity": sev, "quote_found": True})
    if credit_days and credit_days >= 60 and rel in (None, "new"):
        m = re.search(rf"[^.\n]*{credit_days}\s*days?[^.\n]*", text, re.I)
        out.insert(0, {"flag": f"{credit_days} days' credit" + (" for a new buyer" if rel == "new" else ""), "quote": m.group(0).strip()[:300] if m else f"{credit_days} days",
                       "why": "You ship first and wait two months or more to be paid. With a buyer you don't know yet, that's a big risk.",
                       "severity": "high", "quote_found": True})
    return out[:8]


def read(text: str, home_country: str | None = None) -> dict:
    """Everything the plain-code reader can find. Values are None where it found nothing."""
    total, currency, unit_price, unit = money(text)
    qty, qty_unit = quantity(text)
    n_containers, size = containers(text)
    pay = payment(text)
    rel = relationship(text)
    return {
        **route(text, home_country),
        "value": total, "currency": currency, "unit_price": unit_price, "price_unit": unit,
        "quantity": qty, "quantity_unit": qty_unit, "containers": n_containers, "container_size": size,
        "mode": mode(text) or ("sea_container" if n_containers or re.search(r"\b(FOB|CFR|CIF|FAS)\b|bill of lading|\bB/L\b", text) else None),
        "incoterm_mentioned": incoterm(text), "payment_kind": pay["kind"], "credit_days": pay["credit_days"],
        "payment_terms_mentioned": pay["mentioned"], "relationship": rel, "buyer_name": (bn := buyer_name(text)),
        "buyer_address": buyer_address(text, bn), "ship_window": ship_window(text),
        "organic": bool(re.search(r"\borganic\b", text, re.I)),
        "red_flags": risks(text, pay["credit_days"], rel),
    }
