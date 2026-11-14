"""Deal passes: the documents unlock with a pass for one product to one market.

A pass is a signed token, so the server can check it without a database:
    base64(json{scope, exp, via}) + "." + HMAC-SHA256(secret, payload)
The scope is the product and the destination country, so one pass covers every edit and re-run of that
export project, but not a different product or market.

This is a demo checkout: no card is charged. In production the token would be issued by the payment
provider's webhook (Stripe, for example) after a successful payment, or by a sponsor's (bank's or chamber's) code.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time

SECRET = (os.getenv("PAYWALL_SECRET") or secrets.token_hex(32)).encode()
ENABLED = os.getenv("PAYWALL", "on").lower() not in ("off", "0", "false", "no")
PRICE = float(os.getenv("DEAL_PASS_PRICE", "29"))
CURRENCY = os.getenv("DEAL_PASS_CURRENCY", "USD")
DAYS = int(os.getenv("DEAL_PASS_DAYS", "90"))
# Codes a bank, chamber or export agency gives its businesses: their access is paid for (One Click's Export Ready tier).
SPONSOR_CODES = {c.strip().upper(): name.strip() for c, _, name in
                 (x.partition(":") for x in os.getenv("SPONSOR_CODES", "CHAMBER-DEMO:Your chamber of commerce,BANK-DEMO:Your bank").split(","))
                 if c.strip()}


def offer() -> dict:
    return {"price": PRICE, "currency": CURRENCY, "days": DAYS, "covers": "One product to one market",
            "includes": ["Quotation, proforma invoice and packing list", "Print or save as PDF",
                         "Unlimited edits and re-checks for this product and market", f"Valid for {DAYS} days"],
            "demo": True}


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def scope(product_key: str | None, product: str | None, destination: str | None) -> str:
    """What a pass covers: the product family (coffee, not "green coffee") and the destination country,
    so answering "green or roasted?" or editing the wording doesn't break a pass already bought."""
    if product_key:
        family = product_key.split("_")[0]
    else:
        words = [w for w in _norm(product).split() if w not in ("organic", "fresh", "premium", "the", "a")]
        family = words[0] if words else ""
    return f"{family}|{_norm(destination)}"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(scope_: str, via: str = "demo", days: int | None = None) -> dict:
    exp = int(time.time()) + 86400 * (days or DAYS)
    payload = _b64(json.dumps({"s": scope_, "e": exp, "v": via}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
    return {"token": f"{payload}.{sig}", "scope": scope_, "expires": exp, "via": via}


def check(token: str, scope_: str) -> dict | None:
    """The pass's details if the token is genuine, unexpired and covers this scope, else None."""
    try:
        payload, sig = token.strip().split(".")
        good = _b64(hmac.new(SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("e", 0) < time.time() or data.get("s") != scope_:
        return None
    return data


def any_valid(header: str | None, scope_: str) -> dict | None:
    """The header can carry several passes, comma-separated; the browser sends all it holds."""
    for t in (header or "").split(",")[:50]:
        if t.strip() and (ok := check(t, scope_)):
            return ok
    return None
