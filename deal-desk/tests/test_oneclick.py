"""One-click flow: product lookup, the plain-code reader, start (what's found, worked out and asked) and the deal pack."""

import json
import os

os.environ["LLM_PROVIDERS"] = "fake"
os.environ["LLM_RATE_LIMIT_WAIT_S"] = "0"

import pytest
from fastapi.testclient import TestClient

from dealdesk import extract, main, oneclick, products
from llm import set_fake_handler

COFFEE = ("I make organic coffee in Colombia and a buyer in Hamburg, Germany wants 2 containers (about 38,000 kg) for €210,000. "
          "It's my first export to them. They want me to ship by sea from Cartagena and pay 60 days after delivery.")
ORDER = ("PURCHASE ORDER 2027-114\nFrom: Kaffee Handel GmbH, Am Sandtorkai 12, 20457 Hamburg, Germany\n"
         "Please supply 19,200 kg green coffee (organic) at USD 4.20 per kg, FOB Buenaventura. Shipment: March 2027.\n"
         "Payment: 30% advance, balance against copy of B/L. Please use our new bank account details.")


@pytest.fixture
def client():
    main._hits.clear()
    yield TestClient(main.app)
    set_fake_handler(None)


# --- product lookup -------------------------------------------------------------------

@pytest.mark.parametrize("text,key", [
    ("green coffee beans", "coffee_green"), ("decaffeinated green coffee", "coffee_green_decaf"), ("roasted coffee", "coffee_roasted"),
    ("organic coffee", "coffee"), ("fresh mangoes", "mangoes"), ("cotton t-shirts", "tshirts"), ("raw cotton", "cotton"),
    ("rosé wine", "wine"), ("leather handbags", "leather_handbags"),
])
def test_product_lookup(text, key):
    assert products.find(text).key == key


@pytest.mark.parametrize("text", ["limited time offer", "our team", "price list", "grapefruit juice"])
def test_product_lookup_ignores_lookalike_words(text):
    assert products.find(text) is None


def test_colombian_green_coffee_ships_in_70kg_bags():
    assert products.package_for(products.BY_KEY["coffee_green"], "Colombia") == (70.0, "bags")
    assert products.package_for(products.BY_KEY["coffee_green"], "Brazil") == (60, "bags")


def test_eu_destination_adds_eudr_and_organic_documents():
    docs = [d["doc"] for d in products.product_documents(products.BY_KEY["coffee_green"], "Germany", organic=True)]
    assert "Phytosanitary certificate" in docs and "Certificate of inspection for organic goods" in docs
    assert any("EUDR" in d for d in docs)
    assert not any("EUDR" in d["doc"] for d in products.product_documents(products.BY_KEY["coffee_green"], "Japan", False))


# --- plain-code reader --------------------------------------------------------------------

def test_reader_finds_the_coffee_deal():
    r = extract.read(COFFEE)
    assert (r["origin_country"], r["origin_place"], r["destination_country"], r["destination_place"]) == ("Colombia", "Cartagena", "Germany", "Hamburg")
    assert (r["value"], r["currency"], r["quantity"], r["containers"]) == (210000, "EUR", 38000, 2)
    assert (r["payment_kind"], r["credit_days"], r["relationship"], r["organic"]) == ("open", 60, "new", True)
    assert r["red_flags"][0]["flag"].startswith("60 days' credit")


def test_reader_finds_an_order():
    r = extract.read(ORDER)
    assert r["buyer_name"] == "Kaffee Handel GmbH" and r["buyer_address"].startswith("Am Sandtorkai 12")
    assert (r["unit_price"], r["price_unit"], r["quantity"]) == (4.2, "kg", 19200)
    assert r["incoterm_mentioned"] == "FOB Buenaventura" and r["ship_window"] == "March 2027"
    assert r["mode"] == "sea_container" and r["payment_kind"] == "advance"
    assert any(f["flag"] == "Changed bank details" for f in r["red_flags"])


@pytest.mark.parametrize("text,expected", [
    ("Our customer in Japan wants 500 cartons", (None, "Japan")),
    ("Selling to a buyer in Hamburg", (None, "Germany")),
    ("We grow avocados in Peru. A chain in the UK wants them", ("Peru", "United Kingdom")),
])
def test_reader_route(text, expected):
    r = extract.route(text)
    assert (r["origin_country"], r["destination_country"]) == expected


def test_reader_money_formats():
    assert extract.money("total 210.000 EUR")[:2] == (210000, "EUR")
    assert extract.money("USD 1.5 million")[:2] == (1_500_000, "USD")
    assert extract.money("at $3.10 per kg")[2:] == (3.1, "kg")


# --- start: found, worked out, asked -----------------------------------------------------------

def test_start_works_out_and_asks_only_what_is_missing():
    r = oneclick.start(COFFEE)
    f = r["fields"]
    assert f["unit_price"]["source"] == "worked_out" and round(f["unit_price"]["value"], 2) == 5.53
    assert f["hs_code"]["value"] == "0901" and f["package_kg"]["source"] == "assumed"
    assert f["destination_risk"]["value"] == "low"
    assert [q["id"] for q in r["questions"]] == ["product_form", "transport"]
    green = r["questions"][0]["options"][0]["set"]
    assert green["hs_code"] == "090111" and green["product"].startswith("Organic green coffee")


def test_start_never_asks_more_than_three_and_assumes_safely():
    r = oneclick.start("Selling some goods abroad soon.")
    assert len(r["questions"]) == 3
    assert r["fields"]["transport_by"]["source"] == "assumed" and r["fields"]["relationship"]["value"] == "new"


def test_start_reads_the_buyers_delivery_term():
    f = oneclick.start(ORDER)["fields"]
    assert f["value"]["value"] == pytest.approx(80640) and f["value"]["source"] == "worked_out"
    assert f["transport_by"]["value"] == "buyer" and f["incoterm_requested"]["value"] == "FOB Buenaventura"


def test_start_uses_saved_company_details():
    f = oneclick.start("A buyer in Kenya wants 500 boxes of mangoes", {"name": "Mango Co", "country": "Peru"})["fields"]
    assert f["seller_name"] == {"value": "Mango Co", "source": "profile"} and f["origin_country"]["value"] == "Peru"


def test_start_prefers_the_ai_but_keeps_plain_findings():
    reading = {"deal": {"product": "Excelso green coffee", "buyer_name": "Rösterei Nord", "quantity": 19.2, "quantity_unit": "tonnes"}, "red_flags": []}
    f = oneclick.start(COFFEE, None, reading)["fields"]
    assert f["buyer_name"]["value"] == "Rösterei Nord" and f["product_key"]["value"] == "coffee_green"
    assert f["quantity"]["value"] == 19200 and f["quantity_unit"]["value"] == "kg"   # tonnes turned into kg
    assert f["destination_country"]["value"] == "Germany"                           # from the plain reader


# --- the pack -------------------------------------------------------------------------------

def coffee_deal(**kw) -> oneclick.OneDeal:
    base = dict(product="Organic green coffee beans", product_key="coffee_green", hs_code="090111", organic=True,
                origin_country="Colombia", origin_place="Cartagena", destination_country="Germany", destination_place="Hamburg",
                quantity=38000, unit_price=5.5263, value=210000, currency="EUR", containers=2, package_kg=70, package_type="bags",
                relationship="new", destination_risk="low", payment_requested="open", credit_days=60)
    return oneclick.OneDeal(**{**base, **kw})


def levels(p, level):
    return [c["text"] for c in p["checks"] if c["level"] == level]


def test_pack_documents_share_one_set_of_figures():
    p = oneclick.pack(coffee_deal(buyer_name="Kaffee Handel GmbH"))
    q, pi, pl = (p["documents"][k] for k in ("quotation", "proforma", "packing_list"))
    assert q["lines"] == pi["lines"] and q["total"] == pi["total"] == 210000
    assert pl["hs_code"] == q["lines"][0]["hs_code"] == "090111" and pl["net_kg"] == 38000 and pl["packages"] == 543
    assert q["terms"]["delivery"].startswith("FCA [container terminal")
    assert p["incoterm"]["chosen"] == "FCA" and p["payment"]["chosen"] == "lc"


def test_pack_catches_figures_that_dont_add_up():
    p = oneclick.pack(coffee_deal(unit_price=5.0))
    assert any("don't add up" in t for t in levels(p, "fix"))


def test_pack_catches_overloaded_containers():
    assert any("per container" in t for t in levels(oneclick.pack(coffee_deal(containers=1)), "fix"))


def test_pack_explains_fob_with_containers():
    p = oneclick.pack(coffee_deal(incoterm_requested="FOB Buenaventura", transport_by="buyer"))
    assert any("asked for FOB" in t and "containers" in t for t in levels(p, "warn"))


def test_pack_warns_about_credit_for_a_new_buyer_once():
    p = oneclick.pack(coffee_deal(red_flags=[{"flag": "60 days' credit for a new buyer", "why": "Risky."}]))
    assert sum("days' credit" in t for t in levels(p, "warn")) == 1


def test_pack_checklist_and_eu_notes():
    p = oneclick.pack(coffee_deal())
    docs = [d["doc"] for d in p["checklist"]]
    assert "Phytosanitary certificate" in docs and not any(d.startswith("Product-specific") for d in docs)
    assert any("trade agreement" in t for t in levels(p, "ok"))
    assert any("Deforestation" in t for t in levels(p, "warn"))


def test_pack_respects_the_sellers_choices():
    p = oneclick.pack(coffee_deal(incoterm="CIP", payment="advance", deposit_pct=40, transport_by="seller"))
    assert p["incoterm"]["chosen"] == "CIP" and "40% by bank transfer" in p["documents"]["proforma"]["terms"]["payment"]
    assert any("110%" in t for t in levels(p, "ok"))


# --- endpoints ----------------------------------------------------------------------------------

def test_home_is_one_click_and_wizard_still_works(client):
    assert "Paste the buyer" in client.get("/").text
    assert client.get("/wizard").status_code == 200


def test_start_falls_back_when_the_ai_is_busy(client):
    r = client.post("/api/start", data={"text": COFFEE})  # fake provider with no handler: the AI fails
    body = r.json()
    assert r.status_code == 200 and body["reader"] == "rules" and "busy" in body["notice"]
    assert body["fields"]["destination_country"]["value"] == "Germany"


def test_start_with_ai(client):
    set_fake_handler(lambda m: json.dumps({"deal": {"product": "green coffee", "destination_country": "Germany"}, "red_flags": []}))
    body = client.post("/api/start", data={"text": COFFEE}).json()
    assert body["reader"] == "ai" and "notice" not in body and body["fields"]["product_key"]["value"] == "coffee_green"


def test_start_without_ai_never_calls_it(client):
    set_fake_handler(lambda m: pytest.fail("AI should not be called"))
    assert client.post("/api/start", data={"text": COFFEE, "use_ai": "false"}).json()["reader"] == "rules"


def test_start_needs_some_text(client):
    assert client.post("/api/start", data={"text": "hi"}).status_code == 422


# --- the paywall ------------------------------------------------------------------------------

DEAL = {"destination_country": "Germany", "product": "green coffee", "product_key": "coffee_green", "quantity": 1000, "unit_price": 4}


def test_documents_are_locked_but_advice_is_free(client):
    body = client.post("/api/pack", json=DEAL).json()
    assert body["locked"] is True and body["documents"] is None
    assert body["incoterm"]["chosen"] and body["checks"] and body["checklist"]
    assert body["offer"]["price"] > 0 and body["offer"]["demo"] is True


def test_a_pass_unlocks_the_documents(client):
    p = client.post("/api/pass", json={**DEAL, "method": "demo"}).json()
    body = client.post("/api/pack", json=DEAL, headers={"X-Deal-Pass": p["token"]}).json()
    assert body["locked"] is False and body["documents"]["quotation"]["total"] == 4000 and body["pass"]["via"] == "demo"


def test_a_pass_covers_the_product_family_and_market_only(client):
    token = client.post("/api/pass", json={**DEAL, "product_key": "coffee", "product": "coffee"}).json()["token"]
    roasted = {**DEAL, "product_key": "coffee_roasted", "product": "Roasted coffee"}
    assert client.post("/api/pack", json=roasted, headers={"X-Deal-Pass": token}).json()["locked"] is False
    france = {**DEAL, "destination_country": "France"}
    assert client.post("/api/pack", json=france, headers={"X-Deal-Pass": token}).json()["locked"] is True
    cocoa = {**DEAL, "product_key": "cocoa_beans", "product": "Cocoa beans"}
    assert client.post("/api/pack", json=cocoa, headers={"X-Deal-Pass": token}).json()["locked"] is True


def test_any_of_several_passes_works(client):
    other = client.post("/api/pass", json={**DEAL, "destination_country": "Japan"}).json()["token"]
    mine = client.post("/api/pass", json=DEAL).json()["token"]
    assert client.post("/api/pack", json=DEAL, headers={"X-Deal-Pass": f"{other},{mine}"}).json()["locked"] is False


def test_forged_and_expired_passes_are_refused(client):
    from dealdesk import paywall
    good = paywall.issue(paywall.scope("coffee_green", "", "Germany"))["token"]
    payload, sig = good.split(".")
    forged = paywall._b64(json.dumps({"s": "coffee|germany", "e": 9999999999, "v": "demo"}).encode()) + "." + sig
    expired = paywall.issue(paywall.scope("coffee_green", "", "Germany"), days=-1)["token"]
    for t in (forged, expired, "nonsense", ""):
        assert client.post("/api/pack", json=DEAL, headers={"X-Deal-Pass": t}).json()["locked"] is True


def test_sponsor_code(client):
    bad = client.post("/api/pass", json={**DEAL, "method": "code", "code": "WRONG"})
    assert bad.status_code == 422
    ok = client.post("/api/pass", json={**DEAL, "method": "code", "code": "chamber-demo"}).json()
    assert ok["via"] == "sponsor" and ok["sponsor"]
    assert client.post("/api/pack", json=DEAL, headers={"X-Deal-Pass": ok["token"]}).json()["pass"]["via"] == "sponsor"


def test_pass_needs_a_product_and_market(client):
    assert client.post("/api/pass", json={"product": "coffee"}).status_code == 422


def test_paywall_can_be_switched_off(client, monkeypatch):
    from dealdesk import paywall
    monkeypatch.setattr(paywall, "ENABLED", False)
    assert client.post("/api/pack", json=DEAL).json()["documents"]["quotation"]["total"] == 4000
