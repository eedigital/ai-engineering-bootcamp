"""One click: from a buyer's message to a checked deal pack.

1. start(): read the message (plain code always, AI when available), work out what can be worked out,
   and ask at most three questions about the rest. Every field says where it came from.
2. pack(): build the quotation, proforma invoice and packing list from the same figures, the document
   checklist, and the checks that catch mistakes before anything is sent.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import extract, hs, products, rules

LOW_RISK = {"Germany", "France", "Netherlands", "Belgium", "Austria", "Denmark", "Sweden", "Finland", "Ireland", "Luxembourg",
            "Spain", "Italy", "Portugal", "United Kingdom", "Switzerland", "Norway", "United States", "Canada", "Japan",
            "South Korea", "Singapore", "Australia", "New Zealand"}

# Partners with an EU trade agreement or customs union, where proof of origin can lower the duty.
EU_AGREEMENTS = {"Colombia", "Peru", "Ecuador", "Mexico", "Chile", "Costa Rica", "Guatemala", "Honduras", "El Salvador",
                 "Nicaragua", "Panama", "South Africa", "Vietnam", "Japan", "South Korea", "Canada", "Singapore", "Morocco",
                 "Tunisia", "Egypt", "Jordan", "Israel", "Kenya", "Ghana", "Côte d'Ivoire", "Cameroon", "New Zealand",
                 "United Kingdom", "Ukraine", "Turkey", "Switzerland", "Norway"}

Source = Literal["message", "worked_out", "assumed", "profile", "you"]


class OneDeal(BaseModel):
    """Everything the documents need. The page sends this back, edited and confirmed, to /api/pack."""

    product: str = Field(default="", max_length=200)
    product_key: str | None = None
    hs_code: str = Field(default="", max_length=12)
    hs_confirmed: bool = Field(default=False, description="True when the code came from the buyer's order or the seller confirmed it")
    organic: bool = False
    origin_country: str = Field(default="", max_length=60)
    origin_place: str = Field(default="", max_length=80)
    destination_country: str = Field(default="", max_length=60)
    destination_place: str = Field(default="", max_length=80)
    quantity: float | None = Field(default=None, ge=0)
    quantity_unit: str = Field(default="kg", max_length=20)
    unit_price: float | None = Field(default=None, ge=0)
    value: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    containers: int | None = Field(default=None, ge=0, le=500)
    container_size: str | None = Field(default=None, max_length=10)
    package_type: str = Field(default="packages", max_length=30)
    package_kg: float | None = Field(default=None, ge=0)
    mode: rules.Mode = "sea_container"
    transport_by: rules.Party = "buyer"
    delivery_to: Literal["port", "buyer_site"] = "port"
    insurance_by: rules.Party = "seller"
    seller_clears_import: bool = False
    relationship: Literal["new", "some", "established"] = "new"
    destination_risk: Literal["low", "medium", "high", "unsure"] = "unsure"
    buyer_accepts_lc: Literal["yes", "no", "unsure"] = "unsure"
    incoterm_requested: str | None = Field(default=None, max_length=60)
    payment_requested: str | None = Field(default=None, max_length=20)
    credit_days: int | None = Field(default=None, ge=0, le=720)
    incoterm: str | None = Field(default=None, description="The rule the seller chose. Empty means use the recommendation.")
    payment: str | None = Field(default=None, description="The payment method the seller chose. Empty means use the recommendation.")
    deposit_pct: int = Field(default=30, ge=0, le=100)
    buyer_name: str = Field(default="", max_length=120)
    buyer_address: str = Field(default="", max_length=300)
    seller_name: str = Field(default="", max_length=120)
    seller_address: str = Field(default="", max_length=300)
    seller_tax_id: str = Field(default="", max_length=60)
    ship_window: str = Field(default="", max_length=80)
    reference: str = Field(default="", max_length=40)
    red_flags: list[dict] = Field(default_factory=list, max_length=8)


# --- step 1: read and work out ------------------------------------------------------------

def _f(value: Any, source: Source, note: str | None = None) -> dict:
    return {"value": value, "source": source, **({"note": note} if note else {})}


def _transport_from_incoterm(code: str) -> dict:
    c = code.split()[0].upper()
    if c in ("EXW", "FCA", "FAS", "FOB"):
        return {"transport_by": "buyer", "delivery_to": "port"}
    if c in ("CPT", "CIP", "CFR", "CIF"):
        return {"transport_by": "seller", "delivery_to": "port", "insurance_by": "seller" if c in ("CIP", "CIF") else "buyer"}
    return {"transport_by": "seller", "delivery_to": "buyer_site", "seller_clears_import": c == "DDP"}


def start(text: str, profile: dict | None = None, ai_reading: dict | None = None) -> dict:
    """Combine the plain-code reading and (if given) the AI's, work things out, and list the questions to ask."""
    profile = profile or {}
    home = (profile.get("country") or "").strip() or None
    plain = extract.read(text, home)
    ai = (ai_reading or {}).get("deal") or {}
    fields: dict[str, dict] = {}
    unsure_hs: list[dict] = []

    def take(name: str, ai_key: str | None = None, plain_key: str | None = None):
        v = ai.get(ai_key or name)
        if v in (None, "", []):
            v = plain.get(plain_key or name)
        if v not in (None, "", []):
            fields[name] = _f(v, "message")

    for n in ("origin_country", "destination_country", "origin_place", "destination_place", "value", "currency",
              "unit_price", "quantity", "quantity_unit", "containers", "mode", "incoterm_mentioned", "buyer_name"):
        take(n)
    for n in ("buyer_address", "ship_window", "seller_name", "seller_address"):
        if plain.get(n):
            fields[n] = _f(plain[n], "message")
    if not fields.get("ship_window") and ai.get("delivery_date"):
        fields["ship_window"] = _f(ai["delivery_date"], "message")
    if plain.get("container_size"):
        fields["container_size"] = _f(plain["container_size"], "message")
    if plain.get("credit_days"):
        fields["credit_days"] = _f(plain["credit_days"], "message")
    if plain.get("payment_kind"):
        fields["payment_requested"] = _f(plain["payment_kind"], "message")
    if plain.get("organic") or ai.get("organic"):
        fields["organic"] = _f(True, "message")
    rel = plain.get("relationship") or ("new" if ai.get("first_order") else None)
    if rel:
        fields["relationship"] = _f(rel, "message")
    if home:
        fields["origin_country"] = _f(home, "profile")
    for k in ("name", "address", "tax_id"):
        if profile.get(k):
            fields[f"seller_{k}"] = _f(profile[k], "profile")

    # one unit for weights: kg
    u = str((fields.get("quantity_unit") or {}).get("value") or "").lower().strip()
    if u in ("kilogram", "kilograms", "kilos", "kilo", "kgs"):
        fields["quantity_unit"]["value"] = "kg"
    elif u in ("tonne", "tonnes", "ton", "tons", "mt", "metric tons", "metric tonnes", "t") and fields.get("quantity"):
        fields["quantity"]["value"] = round(fields["quantity"]["value"] * 1000, 3)
        fields["quantity_unit"]["value"] = "kg"

    # the product: our table first (reliable), then the AI's description and HS guess
    p = products.find(ai.get("product") or "") or products.find(text)
    phrase = ai.get("product") or plain.get("product_phrase")
    if p:
        fields["product_key"] = _f(p.key, "worked_out")
        name = p.name if not fields.get("organic") else f"Organic {p.name[0].lower()}{p.name[1:]}"
        fields["product"] = _f(ai.get("product") or name, "message" if ai.get("product") else "worked_out")
        fields["hs_code"] = _f(p.hs, "worked_out", _hs_note(p.hs, "Suggested from the product."))
    elif phrase:
        # anything else: search the full HS list, and check the AI's guess is a real code
        fields["product"] = _f(phrase[0].upper() + phrase[1:], "message")
        found = hs.search(phrase, 5)
        guess = ai.get("hs_code_guess")
        if guess and hs.valid(guess) and len(guess) == 6:
            found = [{"code": guess, "description": hs.describe(guess), "sure": True}] + [x for x in found if x["code"] != guess][:4]
        if found:
            top = found[0]["code"]
            opts = [{"code": x["code"], "description": x["description"]} for x in found]
            if found[0].get("sure"):
                fields["hs_code"] = _f(top, "worked_out", _hs_note(top, "Best match in the HS list. Pick another if it's not right."))
            else:
                # a weak match: say so, and ask rather than guess
                fields["hs_code"] = _f(top, "assumed", _hs_note(top, "Not sure. Pick the right one or search."))
                unsure_hs = opts
            fields["hs_code"]["options"] = opts
            fields["product_key"] = _f(f"hs{top}", "worked_out")

    # an HS code written in the order beats our suggestion
    if plain.get("hs_code") and hs.valid(plain["hs_code"]):
        fields["hs_code"] = _f(plain["hs_code"], "message", _hs_note(plain["hs_code"], "From the order."))
        fields["hs_confirmed"] = _f(True, "message")

    # money: fill the gap between quantity, unit price and total
    qty = (fields.get("quantity") or {}).get("value")
    unit = (fields.get("quantity_unit") or {}).get("value")
    up = (fields.get("unit_price") or {}).get("value")
    total = (fields.get("value") or {}).get("value")
    if qty and up and not total:
        fields["value"] = _f(round(qty * up, 2), "worked_out", "Quantity × unit price.")
    elif qty and total and not up:
        fields["unit_price"] = _f(round(total / qty, 4), "worked_out", f"Total ÷ quantity, per {unit or 'unit'}.")

    # packages and containers
    if p and unit == "kg" and qty:
        size, kind = products.package_for(p, (fields.get("origin_country") or {}).get("value"))
        if size:
            fields["package_kg"] = _f(size, "assumed", f"A common size for this product. Change it if yours differ.")
            fields["package_type"] = _f(kind, "assumed")
    if (fields.get("mode") or {}).get("value") == "sea_container" and not fields.get("containers") and qty and unit == "kg":
        fields["containers"] = _f(max(1, math.ceil(qty / 21_000)), "worked_out", "Estimated at about 21 tonnes per 20ft container.")

    # delivery and payment, from what the buyer asked for
    inc = (fields.get("incoterm_mentioned") or {}).get("value")
    if inc:
        fields["incoterm_requested"] = fields.pop("incoterm_mentioned")
        for k, v in _transport_from_incoterm(inc).items():
            fields[k] = _f(v, "message", f"From the buyer's {inc.split()[0].upper()}.")
    if (fields.get("payment_requested") or {}).get("value") == "lc":
        fields["buyer_accepts_lc"] = _f("yes", "message")
    dest = (fields.get("destination_country") or {}).get("value")
    if dest:
        fields["destination_risk"] = _f("low" if dest in LOW_RISK else "unsure", "worked_out",
                                        "Lower-risk market." if dest in LOW_RISK else "Not on our lower-risk list, so treated with care.")
    if not fields.get("mode"):
        fields["mode"] = _f("sea_container", "assumed")

    # questions: only what we can't find or work out, most important first, at most three
    questions: list[dict] = []
    if not dest:
        questions.append({"id": "destination", "text": "Which country is the buyer in?", "input": "country", "field": "destination_country"})
    if not fields.get("product"):
        questions.append({"id": "product", "text": "What are you selling?", "input": "text", "field": "product",
                          "placeholder": "e.g. organic green coffee beans"})
    elif p and p.key == "coffee":
        questions.append({"id": "product_form", "text": "Is the coffee green (not roasted) or roasted?", "field": "product_key",
                          "options": [{"label": "Green, not roasted", "set": _product_set("coffee_green", fields)},
                                      {"label": "Roasted", "set": _product_set("coffee_roasted", fields)}]})
    if unsure_hs:
        questions.append({"id": "hs", "text": f"Which of these best describes your {fields['product']['value'].lower()}?", "field": "hs_code",
                          "options": [{"label": f"{o['code']}: {o['description'][:90]}", "set": {"hs_code": o["code"], "hs_confirmed": True,
                                       "product_key": f"hs{o['code']}"}} for o in unsure_hs[:4]]
                          + [{"label": "None of these: search all codes", "set": {"_search": True}}]})
    if not fields.get("value"):
        questions.append({"id": "value", "text": "What's the total price for this order?", "input": "money", "field": "value"})
    if not fields.get("transport_by"):
        questions.append({"id": "transport", "text": "Who books the main transport?", "field": "transport_by",
                          "options": [{"label": "The buyer does", "set": {"transport_by": "buyer", "delivery_to": "port"}},
                                      {"label": "I do, to their port or airport", "set": {"transport_by": "seller", "delivery_to": "port"}},
                                      {"label": "I do, to their door", "set": {"transport_by": "seller", "delivery_to": "buyer_site"}}]})
    if not fields.get("relationship"):
        questions.append({"id": "relationship", "text": "Have you sold to this buyer before?", "field": "relationship",
                          "options": [{"label": "No, they're new", "set": {"relationship": "new"}},
                                      {"label": "Once or twice", "set": {"relationship": "some"}},
                                      {"label": "Yes, regularly", "set": {"relationship": "established"}}]})
    asked, deferred = questions[:3], questions[3:]
    # what we didn't ask, we assume, safely, and show it as an assumption
    for q in deferred:
        if q["id"] == "transport":
            fields["transport_by"] = _f("buyer", "assumed", "Assumed the buyer books transport. Change it if not.")
        if q["id"] == "relationship":
            fields["relationship"] = _f("new", "assumed", "Assumed a new buyer, the safer choice.")

    flags = (ai_reading or {}).get("red_flags") or plain["red_flags"]
    return {"fields": fields, "questions": asked, "red_flags": flags, "reader": "ai" if ai_reading else "rules"}


def _hs_note(code: str, lead: str) -> str:
    d = hs.describe(code)
    return f"{lead} {hs.EDITION}: {d}" if d else lead


def _product_set(key: str, fields: dict) -> dict:
    p = products.BY_KEY[key]
    organic = bool((fields.get("organic") or {}).get("value"))
    name = f"Organic {p.name[0].lower()}{p.name[1:]}" if organic else p.name
    out = {"product_key": key, "product": name, "hs_code": p.hs}
    if not p.package_kg:
        out.update({"package_kg": None, "package_type": p.package})
    return out


# --- step 2: the deal pack ------------------------------------------------------------------

PAY_TERMS = {
    "advance": lambda d: f"{d.deposit_pct}% by bank transfer on signing, {100 - d.deposit_pct}% before the goods are shipped"
    if 0 < d.deposit_pct < 100 else "100% by bank transfer before the goods are shipped",
    "lc": lambda d: "Irrevocable documentary credit, payable at sight, subject to UCP 600, issued by [buyer's bank]",
    "lc_confirmed": lambda d: "Irrevocable documentary credit, payable at sight, subject to UCP 600, issued by [buyer's bank] and confirmed by [your bank]",
    "collection": lambda d: "Documents against payment (D/P) at sight, subject to URC 522, through [your bank]",
    "open": lambda d: f"Bank transfer {d.credit_days or 30} days after the invoice date",
}
F_GROUP = ("EXW", "FCA", "FAS", "FOB")


def named_place(d: OneDeal, code: str) -> str:
    if code in F_GROUP:
        place, country = d.origin_place, d.origin_country
        if code == "FCA" and d.mode == "sea_container":
            return f"[container terminal or forwarder's warehouse], {place or '[city]'}, {country or '[country]'}"
    else:
        place, country = d.destination_place, d.destination_country
        if code in ("DAP", "DPU", "DDP"):
            return f"[buyer's address], {place or '[city]'}, {country or '[country]'}"
    return ", ".join(x for x in (place or "[port or place]", country) if x)


def _money(v: float | None, cur: str) -> str:
    return f"{cur} {v:,.2f}" if v is not None else f"[{cur} amount]"


def pack(d: OneDeal) -> dict:
    deal = rules.Deal(product=d.product, origin_country=d.origin_country, destination_country=d.destination_country or "the buyer's country",
                      value=d.value, currency=d.currency, buyer_name=d.buyer_name, seller_name=d.seller_name, mode=d.mode,
                      transport_by=d.transport_by, delivery_to=d.delivery_to, insurance_by=d.insurance_by,
                      seller_clears_import=d.seller_clears_import, relationship=d.relationship, destination_risk=d.destination_risk,
                      buyer_accepts_lc=d.buyer_accepts_lc, needs_origin_certificate="unsure")
    plan = rules.plan(deal)
    rec_code = plan["incoterm"]["recommended"]["code"]
    rec_pay = plan["payment"]["recommended"]["key"]
    code = (d.incoterm or rec_code).upper()
    if code not in rules.RULES:
        code = rec_code
    pay = d.payment if d.payment in rules.METHODS else rec_pay
    place = named_place(d, code)
    delivery = f"{code} {place}, Incoterms® 2020"
    p = products.BY_KEY.get(d.product_key or "") or products.find(d.product) or (products.from_hs(d.hs_code, d.product) if d.hs_code else None)

    # one set of figures for every document
    packages = math.ceil(d.quantity / d.package_kg) if d.quantity and d.package_kg and d.quantity_unit == "kg" else None
    package_type = d.package_type
    if packages is None and d.quantity and d.quantity_unit in ("cases", "cartons", "boxes", "bags", "sacks", "bales", "drums", "pallets"):
        packages, package_type = d.quantity, d.quantity_unit
    unit_price = d.unit_price if d.unit_price is not None else (round(d.value / d.quantity, 4) if d.value and d.quantity else None)
    total = d.value if d.value is not None else (round(d.quantity * d.unit_price, 2) if d.quantity and d.unit_price else None)
    ref = d.reference or f"DD-{date.today():%Y%m%d}"
    today = date.today()
    line = {"description": d.product or "[product description]", "hs_code": d.hs_code or "[HS code]",
            "origin": d.origin_country or "[country of origin]", "quantity": d.quantity, "unit": d.quantity_unit,
            "unit_price": unit_price, "amount": total}
    parties = {"seller": {"name": d.seller_name or "[your company name]", "address": d.seller_address or "[your address]",
                          "tax_id": d.seller_tax_id or "[tax ID]"},
               "buyer": {"name": d.buyer_name or "[buyer's company name]", "address": d.buyer_address or "[buyer's address]"}}
    terms = {"delivery": delivery, "payment": PAY_TERMS[pay](d), "payment_rules": rules.METHODS[pay]["rules"],
             "transport": rules.MODE_NAMES[d.mode], "ship_window": d.ship_window or "[shipment window]"}
    docs = {
        "quotation": {"title": "Quotation", "number": f"Q-{ref}", "date": str(today), "valid_until": str(today + timedelta(days=14)),
                      **parties, "lines": [line], "total": total, "currency": d.currency, "terms": terms},
        "proforma": {"title": "Proforma invoice", "number": f"PI-{ref}", "date": str(today), **parties, "lines": [line],
                     "total": total, "currency": d.currency, "terms": terms,
                     "bank": "[your bank name, account number, SWIFT/BIC]",
                     "declaration": f"We declare that the goods are of {d.origin_country or '[country]'} origin."},
        "packing_list": {"title": "Packing list", "number": f"PL-{ref}", "date": str(today), **parties,
                         "description": line["description"], "hs_code": line["hs_code"],
                         "packages": packages, "package_type": package_type, "package_kg": d.package_kg,
                         "net_kg": d.quantity if d.quantity_unit == "kg" else None, "gross_kg": None,
                         "containers": d.containers, "container_size": d.container_size,
                         "marks": f"{(d.buyer_name or 'BUYER').upper()[:20]} / {d.destination_place or d.destination_country or 'DESTINATION'} / {ref}"},
    }

    specific = products.product_documents(p, d.destination_country, d.organic)
    checklist = [x for x in plan["documents"] if not (specific and x["doc"].startswith("Product-specific"))] + specific
    checks = _checks(d, code, rec_code, pay, rec_pay, plan, p, total, unit_price, packages)
    links = [products.duty_link(d.destination_country),
             {"label": "ICC Model International Sale Contract", "url": "https://iccwbo.org/business-solutions/model-contracts-clauses/"},
             {"label": "Find a chamber of commerce for your certificate of origin", "url": "https://iccwbo.org/chamber-services/"}]
    return {"deal": d, "incoterm": {**plan["incoterm"], "chosen": code}, "payment": {**plan["payment"], "chosen": pay},
            "documents": docs, "checklist": checklist, "checks": checks, "links": links, "stages": rules.STAGES,
            "chain": rules._chain(code)}


def _checks(d: OneDeal, code, rec_code, pay, rec_pay, plan, p, total, unit_price, packages) -> list[dict]:
    """Mistakes and gaps, worst first. level: fix (must fix), warn (check), ok (passed)."""
    out: list[dict] = []
    add = lambda level, text: out.append({"level": level, "text": text})  # noqa: E731

    if total is None:
        add("fix", "Add the price: the documents can't go out without it.")
    if d.value and d.quantity and d.unit_price and abs(d.quantity * d.unit_price - d.value) > max(1, d.value * 0.005):
        add("fix", f"The figures don't add up: {d.quantity:,.0f} {d.quantity_unit} × {d.unit_price:,.2f} = "
                   f"{d.quantity * d.unit_price:,.2f}, but the total is {d.value:,.2f}.")
    if not d.destination_country:
        add("fix", "Add the buyer's country.")
    if not d.seller_name:
        add("warn", "Add your company details. They're saved on this device and reused for every deal.")
    if not d.buyer_name:
        add("warn", "Add the buyer's company name and address.")
    if not d.ship_window:
        add("warn", "Add the shipment window, for example “March 2027”.")

    if d.incoterm_requested:
        asked = d.incoterm_requested.split()[0].upper()
        if asked != code:
            reason = ("FOB, CFR and CIF are meant for cargo loaded straight onto the ship. With containers, risk is unclear "
                      "while the box waits at the terminal, so FCA, CPT or CIP fits better." if asked in ("FOB", "CFR", "CIF", "FAS")
                      and d.mode == "sea_container" else plan["incoterm"]["recommended"]["why"][0])
            add("warn", f"The buyer asked for {asked}; the documents use {code}. {reason} Explain the change to the buyer.")
        else:
            add("ok", f"{code} matches what the buyer asked for.")
    if "[" in named_place(d, code):
        add("warn", f"Name the exact place for {code}. Under Incoterms® that's where the cost and risk pass to the buyer.")

    if d.payment_requested == "open" and d.relationship == "new":
        days = f"{d.credit_days} days' " if d.credit_days else ""
        add("warn", f"The buyer wants {days}credit, but they're new. "
                    f"The documents use “{rules.METHODS[pay]['name'].lower()}” instead. Agree it before shipping.")
    elif pay != rec_pay:
        add("warn", f"You chose {rules.METHODS[pay]['name'].lower()}; for this deal we'd suggest {rules.METHODS[rec_pay]['name'].lower()}.")
    if pay.startswith("lc") and code == "FCA":
        add("warn", "Letters of credit usually ask for an on-board bill of lading. Under FCA, agree that the buyer's carrier issues one to you.")
    if code in ("CIF", "CIP") and total:
        add("ok", f"Insure for at least 110% of the price: {d.currency} {total * 1.1:,.2f}.")

    if d.containers and d.quantity and d.quantity_unit == "kg":
        per = d.quantity / d.containers
        if per > 28_000:
            add("fix", f"That's {per:,.0f} kg per container, above what a standard container can usually carry. Check with your forwarder.")
    if packages and d.package_kg and d.quantity and abs(packages * d.package_kg - d.quantity) > 0.01:
        add("warn", f"{d.quantity:,.0f} kg doesn't divide evenly into {d.package_kg:g} kg {d.package_type}: the last one would be part-full.")
    if not d.hs_code:
        add("warn", "Add the HS code. Customs, the buyer and the duty rate all depend on it.")
    elif not hs.valid(d.hs_code):
        add("fix", f"HS code {d.hs_code} isn't in the {hs.EDITION} list. Search for the right one.")
    elif d.hs_confirmed:
        add("ok", f"HS code {d.hs_code} confirmed: {(hs.describe(d.hs_code) or '')[:90]}. The same code is on every document.")
    else:
        add("warn", f"Confirm HS code {d.hs_code} with customs or your broker, and add your country's extra digits.")

    if p and p.eudr and products.in_eu(d.destination_country):
        add("warn", "The EU Deforestation Regulation covers this product. Have the farm's location and deforestation-free proof ready for the buyer.")
    if d.organic and products.in_eu(d.destination_country):
        add("warn", "Organic goods entering the EU need a certificate of inspection in TRACES before they ship.")
    if products.in_eu(d.destination_country) and d.origin_country in EU_AGREEMENTS:
        add("ok", f"{d.origin_country} has a trade agreement with the EU. With proof of origin on your documents, the buyer may pay lower or no duty.")
    credit_warned = d.payment_requested == "open" and d.relationship == "new"
    for f in d.red_flags[:5]:
        if credit_warned and "credit" in str(f.get("flag", "")).lower():
            continue
        add("warn", f"From the buyer's message: {f.get('flag')}. {f.get('why') or ''}".strip())

    add("ok", "The quotation, proforma invoice and packing list use the same product, HS code, quantity and price.")
    order = {"fix": 0, "warn": 1, "ok": 2}
    return sorted(out, key=lambda c: order[c["level"]])
