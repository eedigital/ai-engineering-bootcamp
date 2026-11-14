"""Ask an expert, without leaving the deal.

The business asks for its HS code to be confirmed. The request carries what the deal already knows (product,
route, the codes Deal Desk suggested), so there's no form to fill in. The answer comes back into the same deal.

Prototype: there's no real expert yet. The request is a signed token (no database), and after a short delay a
clearly labelled DEMO answer confirms the best-supported code. In production the request would go to an expert
view used by ICC's network, a chamber or a partner broker, and their answer would be stored and sent back the same way.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from . import hs
from .paywall import SECRET

PRICE = float(os.getenv("EXPERT_PRICE", "15"))
CURRENCY = os.getenv("EXPERT_CURRENCY", "USD")
DEMO_DELAY_S = int(os.getenv("EXPERT_DEMO_DELAY_S", "20"))
PROMISE = "A reply within 24 hours"


def offer() -> dict:
    return {"price": PRICE, "currency": CURRENCY, "promise": PROMISE, "demo": True, "demo_delay_s": DEMO_DELAY_S}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(SECRET, b"expert:" + payload.encode(), hashlib.sha256).digest())


def ask(product: str, codes: list[str], origin: str = "", destination: str = "", question: str = "") -> dict:
    data = {"p": product[:200], "c": [c for c in codes if hs.valid(c)][:6], "o": origin[:60], "d": destination[:60],
            "q": question[:500], "t": int(time.time())}
    payload = _b64(json.dumps(data, separators=(",", ":")).encode())
    return {"id": f"{payload}.{_sign(payload)}", "status": "with_expert", "asked_at": data["t"], "promise": PROMISE}


def status(request_id: str) -> dict | None:
    """None if the id isn't genuine. Otherwise pending, or the (demo) answer once the delay has passed."""
    try:
        payload, sig = request_id.strip().split(".")
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    waited = time.time() - data["t"]
    if waited < DEMO_DELAY_S:
        return {"status": "with_expert", "asked_at": data["t"], "promise": PROMISE}
    # DEMO answer: the suggested code best supported by the full HS list
    found = hs.search(data["p"], 5)
    sure = [x["code"] for x in found if x.get("sure")]
    code = next((c for c in data["c"] if c in sure), None) or (data["c"][0] if data["c"] else (found[0]["code"] if found else None))
    if not code:
        return {"status": "answered", "asked_at": data["t"], "demo": True, "code": None,
                "note": "We need more detail to classify this product: what it's made of and what it's used for."}
    return {"status": "answered", "asked_at": data["t"], "answered_at": data["t"] + DEMO_DELAY_S, "demo": True,
            "code": code, "description": hs.describe(code), "expert": "Demo expert",
            "note": f"For “{data['p']}”, {code} fits: {hs.describe(code)}. Keep a short product sheet (materials, use, a photo) "
                    f"with your records in case customs asks. Your country may add digits after these six."}
