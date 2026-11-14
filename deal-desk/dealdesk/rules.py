"""Deal Desk's rules engine. Plain code, no AI: the same deal always gets the same advice.

Incoterms® is a registered trademark of the International Chamber of Commerce. The summaries
below are our own plain-language descriptions of the Incoterms® 2020 rules, not ICC's text.
The official rules are published by ICC.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["sea_container", "sea_bulk", "air", "road", "rail", "multimodal"]
Party = Literal["seller", "buyer"]


class Deal(BaseModel):
    """One export deal, from the seller's side. Everything has a sensible default except where goods go."""

    product: str = Field(default="", max_length=200)
    origin_country: str = Field(default="", max_length=60)
    destination_country: str = Field(min_length=2, max_length=60)
    value: float | None = Field(default=None, ge=0, le=1e11)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    buyer_name: str = Field(default="", max_length=120)
    seller_name: str = Field(default="", max_length=120)
    # shipping
    mode: Mode = "sea_container"
    transport_by: Party = "seller"
    delivery_to: Literal["port", "buyer_site"] = "port"  # only matters when the seller arranges transport
    insurance_by: Party = "seller"
    seller_clears_import: bool = False
    # the buyer
    relationship: Literal["new", "some", "established"] = "new"
    destination_risk: Literal["low", "medium", "high", "unsure"] = "unsure"
    buyer_accepts_lc: Literal["yes", "no", "unsure"] = "unsure"
    needs_origin_certificate: Literal["yes", "no", "unsure"] = "unsure"


# --- Incoterms® 2020, in our own words ---------------------------------------------

STAGES = [
    "Loading at your site",
    "Export clearance",
    "Transport to the port or terminal",
    "Main transport",
    "Transport to the destination",
    "Import clearance, duties and taxes",
    "Unloading at the destination",
]

# who pays for each stage (S/B), the stage after which risk passes, and our summary
RULES: dict[str, dict] = {
    "EXW": dict(name="Ex Works", modes="any", pays="BBBBBBB", risk_after=0,
                summary="You make the goods available at your site. The buyer collects, loads and handles everything else, including export clearance."),
    "FCA": dict(name="Free Carrier", modes="any", pays="SSBBBBB", risk_after=1,
                summary="You clear the goods for export and hand them to the buyer's carrier at an agreed place, often your own site. Risk and costs pass to the buyer from there."),
    "FAS": dict(name="Free Alongside Ship", modes="sea", pays="SSSBBBB", risk_after=3,
                summary="You clear the goods for export and place them alongside the buyer's ship at the port. Risk passes there."),
    "FOB": dict(name="Free On Board", modes="sea", pays="SSSBBBB", risk_after=3,
                summary="You clear the goods for export and load them on board the buyer's ship at the port. Risk passes once they're on board."),
    "CPT": dict(name="Carriage Paid To", modes="any", pays="SSSSBBB", risk_after=1,
                summary="You pay for transport to the destination, but risk passes to the buyer as soon as you hand the goods to the first carrier."),
    "CIP": dict(name="Carriage and Insurance Paid To", modes="any", pays="SSSSBBB", risk_after=1,
                summary="Like CPT, plus you buy cargo insurance for the buyer. Incoterms® 2020 asks for broad, all-risks level cover here."),
    "CFR": dict(name="Cost and Freight", modes="sea", pays="SSSSBBB", risk_after=3,
                summary="You pay sea freight to the destination port, but risk passes to the buyer once the goods are on board at the origin port."),
    "CIF": dict(name="Cost, Insurance and Freight", modes="sea", pays="SSSSBBB", risk_after=3,
                summary="Like CFR, plus you buy cargo insurance. Incoterms® 2020 only requires minimum cover here, so the buyer may want more."),
    "DAP": dict(name="Delivered at Place", modes="any", pays="SSSSSBB", risk_after=5,
                summary="You deliver to the named destination, ready for unloading. The buyer clears import and pays duties."),
    "DPU": dict(name="Delivered at Place Unloaded", modes="any", pays="SSSSSBS", risk_after=7,
                summary="You deliver to the named destination and unload. The buyer clears import and pays duties."),
    "DDP": dict(name="Delivered Duty Paid", modes="any", pays="SSSSSSB", risk_after=6,
                summary="You deliver to the destination cleared for import, paying duties and taxes. The most work and risk for the seller."),
}
MODE_NAMES = {"sea_container": "sea, in containers", "sea_bulk": "sea, bulk or non-containerised", "air": "air",
              "road": "road", "rail": "rail", "multimodal": "more than one kind of transport"}


def _chain(code: str) -> list[dict]:
    r = RULES[code]
    return [{"stage": s, "pays": "seller" if r["pays"][i] == "S" else "buyer", "risk": "seller" if i < r["risk_after"] else "buyer"}
            for i, s in enumerate(STAGES)]


def _rule(code: str, why: list[str]) -> dict:
    r = RULES[code]
    return {"code": code, "name": r["name"], "label": f"{code} ({r['name']})", "summary": r["summary"],
            "how_to_write": f"{code} [named place] Incoterms® 2020", "why": why, "chain": _chain(code)}


def recommend_incoterm(d: Deal) -> dict:
    """Pick one rule, two alternatives and the warnings that apply. Rules of thumb, in order of priority."""
    why: list[str] = []
    warnings: list[str] = []
    alts: list[tuple[str, str]] = []
    sea_ok = d.mode == "sea_bulk"  # FAS, FOB, CFR and CIF suit non-containerised sea or inland-waterway cargo

    if d.transport_by == "buyer":
        if sea_ok:
            code = "FOB"
            why.append("The buyer books the ship and the cargo isn't in containers, so FOB fits: risk passes once it's on board.")
            alts.append(("FCA", "If you'd rather hand over earlier, at your site or a terminal."))
        else:
            code = "FCA"
            why.append("The buyer arranges transport, so FCA fits: you clear export and hand over to their carrier.")
            if d.mode == "sea_container":
                why.append("For containers, FCA is the right choice instead of FOB: containers are usually handed over at a terminal, not loaded on board by you.")
        why.append("You keep control of export clearance, which you're best placed to handle in your own country.")
        alts.append(("EXW", "Least work for you, but the buyer would need to handle export clearance in your country. Usually best avoided."))
    elif d.delivery_to == "buyer_site":
        if d.seller_clears_import:
            code = "DDP"
            why.append("You deliver to the buyer's door and can handle their import clearance and taxes, so DDP fits.")
            warnings.append("DDP makes you responsible for import duties and taxes such as VAT in the buyer's country. Check whether you must register there before agreeing.")
            alts.append(("DAP", "Same delivery, but the buyer handles import clearance and pays duties. Much less risk for you."))
        else:
            code = "DAP"
            why.append("You deliver to the buyer's door but they handle import clearance and duties, so DAP fits.")
            alts.append(("DDP", "Only if you can clear import and pay taxes in the buyer's country."))
        alts.append(("DPU", "If you also unload the goods at the destination."))
        why.append("Risk stays with you until delivery, so make sure your own insurance covers the whole journey.")
    else:
        insured = d.insurance_by == "seller"
        if sea_ok:
            code = "CIF" if insured else "CFR"
            why.append("You pay sea freight for non-containerised cargo, so " + ("CIF fits, with you buying the insurance." if insured else "CFR fits, with the buyer insuring."))
            alts.append(("CIP" if insured else "CPT", "If the goods move in containers or by more than one kind of transport."))
            if insured:
                warnings.append("CIF only requires minimum insurance cover. If the buyer expects broader cover, agree it in writing.")
        else:
            code = "CIP" if insured else "CPT"
            why.append("You pay for transport to the destination, so " + ("CIP fits, with you buying broad insurance cover." if insured else "CPT fits, with the buyer insuring."))
            if d.mode == "sea_container":
                why.append("For containers, CPT and CIP are the right choice instead of CFR and CIF.")
            alts.append(("DAP", "If you'd rather keep the risk until the goods arrive."))
        warnings.append("Risk passes to the buyer early, when the goods are handed to the first carrier, even though you're paying for transport. Make sure that's clear to the buyer.")
        alts.append(("FCA", "If the buyer would rather book and pay for transport."))

    if d.mode == "sea_container" and not any("containers" in w for w in why):
        warnings.append("Avoid FOB, CFR and CIF for containers. They're designed for cargo loaded directly on board, not containers handed over at a terminal.")
    if code == "FCA" and d.buyer_accepts_lc != "no":
        warnings.append("If you're paid by letter of credit, the bank may want an on-board bill of lading. Under FCA in Incoterms® 2020 you can agree that the buyer's carrier issues one to you.")
    warnings.append("Always name the place precisely, with an address or port, and write “Incoterms® 2020” after it.")

    return {"recommended": _rule(code, why), "alternatives": [{**_rule(c, [w]), "why_short": w} for c, w in alts[:2]],
            "warnings": warnings, "mode": MODE_NAMES[d.mode]}


# --- getting paid ----------------------------------------------------------------------

METHODS = {
    "advance": dict(name="Payment in advance", rules=None,
                    how="The buyer pays all or part before you ship.",
                    protects="You carry no risk of not being paid. Buyers often ask for a deposit-and-balance split instead."),
    "lc": dict(name="Letter of credit", rules="ICC's UCP 600 rules for documentary credits",
               how="The buyer's bank promises to pay once you present the documents the credit asks for.",
               protects="A bank, not the buyer, commits to pay. Documents must match the credit exactly, or payment can be refused."),
    "lc_confirmed": dict(name="Confirmed letter of credit", rules="ICC's UCP 600 rules for documentary credits",
                         how="As a letter of credit, but a bank in your country also guarantees payment.",
                         protects="Protects you even if the buyer's bank or country runs into trouble. Costs more."),
    "collection": dict(name="Documentary collection (documents against payment)", rules="ICC's URC 522 rules for collections",
                       how="Your bank sends the shipping documents to the buyer's bank, which releases them only when the buyer pays.",
                       protects="The buyer can't take the goods without paying, but nothing forces them to pay, so the goods could be left at the port."),
    "open": dict(name="Open account", rules=None,
                 how="You ship first and the buyer pays later, often 30 to 90 days after the invoice.",
                 protects="Easiest for the buyer, riskiest for you. Export credit insurance can cover non-payment."),
}


def recommend_payment(d: Deal) -> dict:
    score = {"new": 2, "some": 1, "established": 0}[d.relationship]
    score += {"low": 0, "medium": 1, "high": 2, "unsure": 1}[d.destination_risk]
    if d.value and d.value >= 100_000:
        score += 1
    notes: list[str] = []

    if score >= 4:
        key, alts = "advance", ["lc_confirmed", "lc"]
    elif score == 3:
        key, alts = ("lc_confirmed" if d.destination_risk == "high" else "lc"), ["advance", "collection"]
    elif score == 2:
        key, alts = "collection", ["lc", "advance"]
    else:
        key, alts = "open", ["collection", "lc"]

    if key.startswith("lc") and d.buyer_accepts_lc == "no":
        notes.append("The buyer won't use a letter of credit, so ask for a deposit before shipping and the balance through a documentary collection.")
        key, alts = "advance", ["collection", "open"]
    if key.startswith("lc") and d.value is not None and d.value < 15_000:
        notes.append("Bank fees can make a letter of credit expensive for a deal this size. A deposit in advance may be simpler.")
    if key == "open":
        notes.append("Consider export credit insurance, and set a credit limit for this buyer.")
    if d.relationship == "new":
        notes.append("Before shipping to a new buyer, check they're a real, registered business, and confirm bank details by phone, never by email alone.")

    reason = {
        "advance": "This is a new buyer or a higher-risk destination, so get paid before the goods leave.",
        "lc": "A bank's promise to pay protects you while you build trust with this buyer.",
        "lc_confirmed": "A higher-risk destination makes a guarantee from a bank in your own country worth the cost.",
        "collection": "You know this buyer somewhat, so keeping control of the documents until they pay is a fair balance.",
        "open": "An established buyer in a lower-risk market is usually offered open account terms.",
    }[key]
    m = METHODS[key]
    return {"recommended": {"key": key, **m, "why": reason}, "alternatives": [{"key": a, **METHODS[a]} for a in alts if a != key][:2],
            "notes": notes, "risk_score": score}


# --- documents ------------------------------------------------------------------------

TRANSPORT_DOC = {
    "sea_container": "Bill of lading or sea waybill, from the shipping line",
    "sea_bulk": "Bill of lading, from the shipping line",
    "air": "Air waybill, from the airline or forwarder",
    "road": "CMR consignment note, from the road carrier",
    "rail": "Rail consignment note, from the rail carrier",
    "multimodal": "Multimodal transport document, from the forwarder",
}


def documents(d: Deal, incoterm: str, payment_key: str) -> list[dict]:
    """What to prepare, and who issues it. `who` is a short label; `note` says why it's needed."""
    out = [
        {"doc": "Commercial invoice", "who": "You", "note": "Must match the contract: goods, price, currency and the Incoterms® rule."},
        {"doc": "Packing list", "who": "You", "note": "What's in each package, with weights and dimensions."},
    ]
    if incoterm != "EXW":
        out.append({"doc": "Export declaration", "who": "You or your forwarder", "note": "Filed with customs in your country before the goods leave."})
    else:
        out.append({"doc": "Export declaration", "who": "The buyer", "note": "Under EXW the buyer files it, but you may still need to supply information."})
    out.append({"doc": TRANSPORT_DOC[d.mode].split(",")[0], "who": TRANSPORT_DOC[d.mode].split(", from ")[-1].capitalize(),
                "note": "Proof the goods were shipped. Banks and buyers rely on it."})
    if incoterm in ("CIF", "CIP"):
        out.append({"doc": "Insurance certificate", "who": "Your insurer", "note": f"You insure the goods under {incoterm}, so the buyer gets proof of cover."})
    if incoterm == "DDP":
        out.append({"doc": "Import declaration and duty payment", "who": "You, through an agent in the buyer's country",
                    "note": "Under DDP you clear import and pay duties and taxes at the destination."})
    if d.needs_origin_certificate in ("yes", "unsure"):
        out.append({"doc": "Certificate of origin", "who": "Your local chamber of commerce",
                    "note": "Proves where the goods were made. Many chambers issue them, often online."
                            + (" Check with the buyer whether one is needed." if d.needs_origin_certificate == "unsure" else ""),
                    "chamber": True})
    if payment_key.startswith("lc"):
        out.append({"doc": "Every document the letter of credit lists", "who": "You",
                    "note": "Banks check documents against the credit word for word. Small differences can delay or stop payment."})
    if payment_key in ("collection",) or payment_key.startswith("lc"):
        out.append({"doc": "Bill of exchange (draft)", "who": "You", "note": "Your formal demand for payment, often required by the bank."})
    out.append({"doc": "Product-specific certificates, if any", "who": "Varies",
                "note": "Some goods need health, plant, safety or conformity certificates. Check the rules for your product in the destination country."})
    return out


# --- draft terms sheet ---------------------------------------------------------------------

def terms_sheet(d: Deal, incoterm: str, payment: dict) -> str:
    money = f"{d.currency} {d.value:,.2f}" if d.value else f"[total price in {d.currency}]"
    place = "[named place: address or port]"
    return "\n".join([
        "DRAFT TERMS OF SALE (for discussion, not a contract)",
        "",
        f"Seller: {d.seller_name or '[your company name and address]'}",
        f"Buyer: {d.buyer_name or '[buyer company name and address]'}",
        f"Goods: {d.product or '[description, quantity and specification]'}",
        f"Total price: {money}",
        f"Delivery: {incoterm} {place} Incoterms® 2020",
        f"Transport: by {MODE_NAMES[d.mode]}",
        "Delivery date: [date or shipment window]",
        f"Payment: {payment['recommended']['name']}" + (f", under {payment['recommended']['rules']}" if payment["recommended"]["rules"] else "") + ". [timing, e.g. 30% deposit, 70% before shipment]",
        "Documents: commercial invoice, packing list, transport document [add others agreed]",
        "Inspection: [who inspects, where and when]",
        "Governing law: [country]",
        "Disputes: [how disputes are resolved, e.g. arbitration]",
        "",
        "For a complete contract, use a professionally drafted template such as the ICC Model International Sale Contract, and take legal advice.",
    ])


def plan(d: Deal) -> dict:
    inc = recommend_incoterm(d)
    pay = recommend_payment(d)
    return {
        "deal": d,
        "incoterm": inc,
        "payment": pay,
        "documents": documents(d, inc["recommended"]["code"], pay["recommended"]["key"]),
        "terms_sheet": terms_sheet(d, inc["recommended"]["code"], pay),
        "stages": STAGES,
    }
