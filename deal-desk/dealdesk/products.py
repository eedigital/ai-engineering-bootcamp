"""Product lookup: plain words -> a suggested HS code and what the product needs.

HS codes here are the international 6-digit level, which every country shares. Countries add
their own digits after these six, so a customs broker or the customs website should confirm
the full code. Every suggestion is labelled as one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EU = {
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czechia", "czech republic", "denmark", "estonia",
    "finland", "france", "germany", "greece", "hungary", "ireland", "italy", "latvia", "lithuania", "luxembourg",
    "malta", "netherlands", "poland", "portugal", "romania", "slovakia", "slovenia", "spain", "sweden",
}

# Commodities covered by the EU Deforestation Regulation (EUDR), including products made from them.
EUDR = {"coffee", "cocoa", "palm", "soy", "rubber", "wood", "cattle"}


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    hs: str  # 6-digit HS code
    words: tuple[str, ...]  # all must appear (any order) for a match
    avoid: tuple[str, ...] = ()  # none of these may appear
    plant: bool = False  # plant product: a phytosanitary certificate is often required
    animal: bool = False  # animal product: a health certificate is usually required
    food: bool = False
    eudr: str | None = None
    package_kg: float | None = None  # a common package size, offered as an assumption to confirm
    package: str = "packages"
    ask: tuple[str, ...] = ()  # keys of close variants to choose between when the text is vague
    notes: tuple[str, ...] = field(default=())


P = Product
PRODUCTS: list[Product] = [
    # coffee: green (unroasted) vs roasted is the first question every buyer and customs officer asks
    P("coffee_green", "Green coffee beans, not roasted, not decaffeinated", "090111", ("coffee", "green"), ("decaf*",),
      plant=True, food=True, eudr="coffee", package_kg=60, package="bags", ask=("coffee_green", "coffee_roasted")),
    P("coffee_green_decaf", "Green coffee beans, not roasted, decaffeinated", "090112", ("coffee", "green", "decaf*"),
      plant=True, food=True, eudr="coffee", package_kg=60, package="bags"),
    P("coffee_roasted", "Roasted coffee, not decaffeinated", "090121", ("coffee", "roasted"), ("decaf*",),
      food=True, eudr="coffee", package="bags", ask=("coffee_green", "coffee_roasted")),
    P("coffee_instant", "Instant coffee (coffee extract)", "210111", ("coffee", "instant"), food=True, eudr="coffee", package="cartons"),
    P("coffee", "Coffee", "0901", ("coffee",), plant=True, food=True, eudr="coffee", package_kg=60, package="bags",
      ask=("coffee_green", "coffee_roasted")),
    P("cocoa_beans", "Cocoa beans, whole or broken, raw or roasted", "180100", ("cocoa", "bean"), plant=True, food=True,
      eudr="cocoa", package_kg=62.5, package="bags"),
    P("cocoa_powder", "Cocoa powder, unsweetened", "180500", ("cocoa", "powder"), food=True, eudr="cocoa", package="bags"),
    P("cocoa_butter", "Cocoa butter", "180400", ("cocoa", "butter"), food=True, eudr="cocoa", package="cartons"),
    P("chocolate", "Chocolate and food preparations containing cocoa", "1806", ("chocolate",), food=True, eudr="cocoa", package="cartons"),
    P("bananas", "Bananas, fresh", "080390", ("banana",), ("plantain",), plant=True, food=True, package_kg=18.14, package="boxes"),
    P("plantains", "Plantains, fresh", "080310", ("plantain",), plant=True, food=True, package="boxes"),
    P("avocados", "Avocados, fresh", "080440", ("avocado",), plant=True, food=True, package_kg=4, package="boxes"),
    P("mangoes", "Mangoes, fresh", "080450", ("mango",), plant=True, food=True, package_kg=4, package="boxes"),
    P("pineapples", "Pineapples, fresh", "080430", ("pineapple",), plant=True, food=True, package="boxes"),
    P("blueberries", "Blueberries, fresh", "081040", ("blueberr*",), plant=True, food=True, package="boxes"),
    P("grapes", "Grapes, fresh", "080610", ("grape",), ("raisin", "wine"), plant=True, food=True, package="boxes"),
    P("oranges", "Oranges, fresh", "080510", ("orange",), ("juice",), plant=True, food=True, package="boxes"),
    P("lemons", "Lemons and limes, fresh", "080550", ("lemon",), plant=True, food=True, package="boxes"),
    P("limes", "Lemons and limes, fresh", "080550", ("lime",), plant=True, food=True, package="boxes"),
    P("roses", "Roses, cut flowers, fresh", "060311", ("rose",), ("wine",), plant=True, package="boxes"),
    P("carnations", "Carnations, cut flowers, fresh", "060312", ("carnation",), plant=True, package="boxes"),
    P("flowers", "Cut flowers, fresh", "060319", ("flower",), plant=True, package="boxes"),
    P("cashews", "Cashew nuts, shelled", "080132", ("cashew",), ("shell",), plant=True, food=True, package="cartons"),
    P("quinoa", "Quinoa", "100850", ("quinoa",), plant=True, food=True, package="bags"),
    P("rice", "Rice", "1006", ("rice",), plant=True, food=True, package="bags"),
    P("black_tea", "Black tea, in packages over 3 kg", "090240", ("black", "tea"), plant=True, food=True, package="sacks"),
    P("green_tea", "Green tea, in packages over 3 kg", "090220", ("green", "tea"), plant=True, food=True, package="sacks"),
    P("tea", "Tea", "0902", ("tea",), plant=True, food=True, package="sacks"),
    P("pepper", "Black pepper, neither crushed nor ground", "090411", ("pepper",), ("bell", "chili", "chilli", "ground"), plant=True, food=True, package="bags"),
    P("vanilla", "Vanilla", "090500", ("vanilla",), plant=True, food=True, package="cartons"),
    P("ginger", "Ginger, neither crushed nor ground", "091011", ("ginger",), plant=True, food=True, package="cartons"),
    P("cinnamon", "Cinnamon", "0906", ("cinnamon",), plant=True, food=True, package="cartons"),
    P("raw_sugar", "Raw cane sugar", "170114", ("sugar",), food=True, package="bags"),
    P("honey", "Natural honey", "040900", ("honey",), animal=True, food=True, package="drums"),
    P("olive_oil", "Extra virgin olive oil", "150920", ("olive", "oil"), food=True, package="cartons"),
    P("palm_oil", "Crude palm oil", "151110", ("palm", "oil"), food=True, eudr="palm", package="flexitanks"),
    P("soybeans", "Soya beans", "120190", ("soy",), plant=True, food=True, eudr="soy", package="tonnes in bulk"),
    P("wine", "Wine, in bottles of 2 litres or less", "220421", ("wine",), food=True, package="cases"),
    P("rum", "Rum", "220840", ("rum",), food=True, package="cases"),
    P("shrimp", "Shrimps and prawns, frozen", "030617", ("shrimp",), animal=True, food=True, package="cartons"),
    P("prawns", "Shrimps and prawns, frozen", "030617", ("prawn",), animal=True, food=True, package="cartons"),
    P("tuna_canned", "Tuna, prepared or preserved (canned)", "160414", ("tuna",), animal=True, food=True, package="cartons"),
    P("beef", "Beef, fresh or chilled, boneless", "020130", ("beef",), animal=True, food=True, eudr="cattle", package="cartons"),
    P("leather_bags", "Handbags with an outer surface of leather", "420221", ("leather", "bag"), eudr="cattle", package="cartons"),
    P("leather_handbags", "Handbags with an outer surface of leather", "420221", ("leather", "handbag"), eudr="cattle", package="cartons"),
    P("tshirts", "T-shirts, knitted, of cotton", "610910", ("shirt",), package="cartons"),
    P("cotton", "Raw cotton, not carded or combed", "520100", ("cotton",), ("shirt", "t"), plant=True, package="bales"),
    P("natural_rubber", "Natural rubber", "4001", ("rubber",), eudr="rubber", package="bales"),
    P("sawn_wood", "Sawn wood", "4407", ("sawn",), plant=True, eudr="wood", package="bundles"),
    P("wood_furniture", "Wooden furniture", "940360", ("furniture",), eudr="wood", package="packages"),
    P("cosmetics", "Beauty and skin-care preparations", "3304", ("cosmetic",), package="cartons"),
]
BY_KEY = {p.key: p for p in PRODUCTS}


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()) + " "


def _has(t: str, w: str) -> bool:
    """Whole word, allowing plurals ("mangoes", "limes"). A trailing * matches any ending ("decaf*")."""
    if w.endswith("*"):
        return f" {w[:-1]}" in t
    return re.search(rf" {re.escape(w)}(s|es)? ", t) is not None


def find(text: str) -> Product | None:
    """The most specific product whose words all appear in the text, or None."""
    t = _norm(text)
    best: tuple[int, Product] | None = None
    for p in PRODUCTS:
        if all(_has(t, w) for w in p.words) and not any(_has(t, a) for a in p.avoid):
            score = sum(len(w) for w in p.words)
            if best is None or score > best[0]:
                best = (score, p)
    return best[1] if best else None


def from_hs(code: str, name: str = "") -> Product | None:
    """A product outside our list, described by its HS code. Its needs (plant, animal, EUDR) come from the HS chapter."""
    from . import hs
    c = "".join(ch for ch in code or "" if ch.isdigit())[:6]
    if not hs.valid(c):
        return None
    n = hs.needs(c)
    return Product(key=f"hs{c}", name=name or hs.describe(c) or c, hs=c, words=(), plant=n["plant"], animal=n["animal"],
                   food=n["food"], eudr=n["eudr"], package="packages")


def package_for(p: Product, origin: str | None) -> tuple[float | None, str]:
    """A common package size to offer as an assumption. Colombian green coffee usually ships in 70 kg bags."""
    if p.key.startswith("coffee_green") or p.key == "coffee":
        if (origin or "").strip().lower() == "colombia":
            return 70.0, "bags"
    return p.package_kg, p.package


def in_eu(country: str | None) -> bool:
    return (country or "").strip().lower() in EU


def product_documents(p: Product | None, destination: str | None, organic: bool) -> list[dict]:
    """Documents the product itself may need, on top of the deal's standard documents."""
    if p is None:
        return []
    out: list[dict] = []
    eu = in_eu(destination)
    if p.plant:
        out.append({"doc": "Phytosanitary certificate", "who": "Your country's plant health authority",
                    "note": "Plant products often need one. Confirm whether the destination requires it for this product."})
    if p.animal:
        out.append({"doc": "Health certificate", "who": "Your country's veterinary or food safety authority",
                    "note": "Animal products usually need one, and your country and producer may need to be approved by the destination."})
    if organic:
        if eu:
            out.append({"doc": "Certificate of inspection for organic goods", "who": "Your organic certification body, in the EU's TRACES system",
                        "note": "Without it, the goods can't be sold as organic in the EU."})
        else:
            out.append({"doc": "Organic certificate", "who": "Your organic certification body",
                        "note": "Check that your certification is recognised in the destination country."})
    if p.eudr and eu:
        out.append({"doc": "EU deforestation (EUDR) information", "who": "You, for the buyer's due diligence statement",
                    "note": f"{p.eudr.capitalize()} is covered by the EU Deforestation Regulation. Buyers ask for the plot location (geolocation) "
                            "and proof the land wasn't deforested. Check the current application dates."})
    return out


def duty_link(destination: str | None) -> dict:
    if in_eu(destination):
        return {"label": "Check the import duty on Access2Markets (EU)", "url": "https://trade.ec.europa.eu/access-to-markets/en/home"}
    return {"label": "Check the import duty on Market Access Map", "url": "https://www.macmap.org/"}
