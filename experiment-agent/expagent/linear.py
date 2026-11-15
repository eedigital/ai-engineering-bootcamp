"""Talking to Linear: webhook verification, tokens, and agent activities.

Docs: https://linear.app/developers/agents and https://linear.app/developers/agent-interaction
- Webhooks are signed: Linear-Signature = hex HMAC-SHA256 of the raw body with the webhook secret, and the body's
  webhookTimestamp (ms) should be within a minute of now.
- The agent replies by creating Agent Activities on the session: thought, action, response, elicitation, error.
  A thought within 10 seconds of a 'created' event stops the session being marked unresponsive.
- Tokens: the app is installed once with actor=app (so it appears in @-mentions). After that the server mints
  app-actor tokens with the client_credentials grant (valid 30 days) whenever it needs one, so nothing has to be
  stored. If client credentials aren't enabled, it falls back to the token from the install, kept in memory.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time

import httpx

log = logging.getLogger("expagent")

GRAPHQL = "https://api.linear.app/graphql"
TOKEN_URL = "https://api.linear.app/oauth/token"
AUTHORIZE_URL = "https://linear.app/oauth/authorize"
SCOPES = "read,write,comments:create,app:mentionable,app:assignable"


def client_id() -> str:
    return os.getenv("LINEAR_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.getenv("LINEAR_CLIENT_SECRET", "").strip()


def webhook_secret() -> str:
    return os.getenv("LINEAR_WEBHOOK_SECRET", "").strip()


def configured() -> dict:
    return {"client_id": bool(client_id()), "client_secret": bool(client_secret()), "webhook_secret": bool(webhook_secret())}


# --- webhooks -------------------------------------------------------------------------------

def verify(raw: bytes, signature: str | None, max_age_s: int = 60, now_ms: float | None = None) -> tuple[bool, str]:
    secret = webhook_secret()
    if not secret:
        return False, "LINEAR_WEBHOOK_SECRET isn't set"
    if not signature:
        return False, "missing Linear-Signature header"
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.strip(), expected):
        return False, "bad signature"
    try:
        ts = json.loads(raw).get("webhookTimestamp")
    except ValueError:
        return False, "body isn't JSON"
    now = now_ms if now_ms is not None else time.time() * 1000
    if not isinstance(ts, (int, float)) or abs(now - ts) > max_age_s * 1000:
        return False, "stale or missing webhookTimestamp"
    return True, "ok"


class Seen:
    """Linear can deliver the same webhook twice; reply once. In memory: fine for one free instance."""

    def __init__(self, size: int = 500):
        self._ids: dict[str, float] = {}
        self._size = size
        self._lock = threading.Lock()

    def first_time(self, key: str) -> bool:
        with self._lock:
            if key in self._ids:
                return False
            if len(self._ids) >= self._size:
                for k in sorted(self._ids, key=self._ids.get)[: self._size // 2]:
                    del self._ids[k]
            self._ids[key] = time.time()
            return True


# --- tokens ---------------------------------------------------------------------------------

_token: dict = {"value": None, "expires": 0.0, "source": None}
_install_token: dict = {"value": None, "expires": 0.0}
_token_lock = threading.Lock()


def authorize_url(redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode
    return AUTHORIZE_URL + "?" + urlencode({"client_id": client_id(), "redirect_uri": redirect_uri, "response_type": "code",
                                            "scope": SCOPES, "state": state, "actor": "app", "prompt": "consent"})


def exchange_code(code: str, redirect_uri: str) -> dict:
    """Finish the install. Keeps the token in memory as a fallback, and returns the app's identity."""
    r = httpx.post(TOKEN_URL, data={"code": code, "redirect_uri": redirect_uri, "client_id": client_id(),
                                    "client_secret": client_secret(), "grant_type": "authorization_code"}, timeout=20)
    r.raise_for_status()
    body = r.json()
    _install_token.update(value=body["access_token"], expires=time.time() + float(body.get("expires_in", 86_000)) - 300)
    me = graphql("query { viewer { id name } organization { name urlKey } }", token=body["access_token"])
    return me


def _client_credentials() -> tuple[str, float] | None:
    if not (client_id() and client_secret()):
        return None
    r = httpx.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": client_id(), "client_secret": client_secret(),
                                    "scope": "read,write,comments:create"}, timeout=20)
    if r.status_code != 200:
        log.warning("client_credentials_failed status=%s body=%s", r.status_code, r.text[:300])
        return None
    body = r.json()
    return body["access_token"], time.time() + float(body.get("expires_in", 30 * 86_400)) - 600


def token(force_new: bool = False) -> str:
    with _token_lock:
        if not force_new and _token["value"] and _token["expires"] > time.time():
            return _token["value"]
        cc = _client_credentials()
        if cc:
            _token.update(value=cc[0], expires=cc[1], source="client_credentials")
            return cc[0]
        if _install_token["value"] and _install_token["expires"] > time.time():
            _token.update(value=_install_token["value"], expires=_install_token["expires"], source="install")
            return _install_token["value"]
        key = os.getenv("LINEAR_API_KEY")  # last resort for local testing
        if key:
            return key
    raise RuntimeError("No Linear token: set LINEAR_CLIENT_ID and LINEAR_CLIENT_SECRET and turn on client credentials, "
                       "or install the app again from the home page")


def graphql(query: str, variables: dict | None = None, token: str | None = None) -> dict:
    tok = token or globals()["token"]()
    auth = tok if tok.startswith("lin_api_") else f"Bearer {tok}"
    r = httpx.post(GRAPHQL, json={"query": query, "variables": variables or {}}, headers={"Authorization": auth}, timeout=20)
    if r.status_code == 401 and token is None:  # the token was replaced: mint a new one and retry once
        tok = globals()["token"](force_new=True)
        r = httpx.post(GRAPHQL, json={"query": query, "variables": variables or {}},
                       headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"Linear API error: {body['errors'][0].get('message')}")
    return body["data"]


# --- agent activities -------------------------------------------------------------------------

ACTIVITY = """mutation AgentActivityCreate($input: AgentActivityCreateInput!) {
  agentActivityCreate(input: $input) { success }
}"""


def activity(session_id: str, content: dict, ephemeral: bool = False) -> None:
    payload = {"agentSessionId": session_id, "content": content}
    if ephemeral and content.get("type") in ("thought", "action"):
        payload["ephemeral"] = True
    graphql(ACTIVITY, {"input": payload})


def thought(session_id: str, body: str, ephemeral: bool = False) -> None:
    activity(session_id, {"type": "thought", "body": body}, ephemeral)


def action(session_id: str, name: str, parameter: str, result: str | None = None) -> None:
    content = {"type": "action", "action": name, "parameter": parameter}
    if result is not None:
        content["result"] = result
    activity(session_id, content)


def response(session_id: str, body: str) -> None:
    activity(session_id, {"type": "response", "body": body})


def error(session_id: str, body: str) -> None:
    activity(session_id, {"type": "error", "body": body})
