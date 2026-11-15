"""Experiment Designer: a Linear agent that turns an issue into an A/B test plan.

@mention it on an issue like "Test shorter checkout" and it replies in the issue with a hypothesis, the sample size
and how long to run, guardrail metrics, and a PostHog query to measure the result.

Routes:
  GET  /                  home page: what it does, setup status, and a try-it box (no Linear needed)
  POST /api/design        the same plan from plain text, as JSON and Markdown
  GET  /install           installs the agent in a Linear workspace (admin, actor=app)
  GET  /oauth/callback    finishes the install
  POST /webhooks/linear   Linear's AgentSessionEvent webhooks
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import design, linear

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("expagent")

app = FastAPI(title="Experiment Designer", version="1.0")


@app.on_event("startup")
def _mint_token() -> None:
    """Fetch an app token with all five scopes at start, so the app keeps its mention and assign permissions."""
    if not (linear.client_id() and linear.client_secret()):
        return
    import threading

    def run() -> None:
        try:
            linear.token(force_new=True)
            log.info("startup_token ok scopes=%s", linear.SCOPES)
        except Exception as e:  # noqa: BLE001
            log.warning("startup_token_failed %s", e)
    threading.Thread(target=run, daemon=True).start()
STATIC = Path(__file__).parent / "static"
STATE_SECRET = (os.getenv("STATE_SECRET") or secrets.token_hex(16)).encode()
seen = linear.Seen()
sessions: dict[str, dict] = {}  # session id -> {"context": issue text, "extra": replies so far}
_hits: dict[str, deque] = defaultdict(deque)


def _limited(request: Request, limit: int = 30) -> JSONResponse | None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        return JSONResponse(status_code=429, content={"error": "Too many requests. Wait a minute."})
    q.append(now)
    return None


def _base(request: Request) -> str:
    """The public address, for the OAuth callback. Render terminates HTTPS in front of the app."""
    if os.getenv("PUBLIC_URL"):
        return os.environ["PUBLIC_URL"].rstrip("/")
    url = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto") == "https" or url.endswith(".onrender.com"):
        url = url.replace("http://", "https://", 1)
    return url


@app.get("/health")
def health():
    return {"status": "ok", "linear": linear.configured()}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html", media_type="text/html")


@app.get("/api/status")
def status(request: Request):
    base = _base(request)
    return {"configured": linear.configured(), "callback_url": f"{base}/oauth/callback", "webhook_url": f"{base}/webhooks/linear",
            "installed_token": linear._token.get("source")}


# --- try it without Linear ------------------------------------------------------------------------

class DesignRequest(BaseModel):
    text: str = Field(min_length=3, max_length=8000)
    follow_up: str = Field(default="", max_length=2000)
    use_ai: bool = True


@app.post("/api/design")
def api_design(req: DesignRequest, request: Request):
    if (r := _limited(request)):
        return r
    out = design.build(req.text, req.follow_up, use_ai=req.use_ai)
    p = out.get("plan")
    return {"markdown": out["markdown"], "assumed": out["assumed"], "words_source": out.get("words_source"),
            "plan": None if p is None else {"per_variant": p.per_variant, "total": p.total, "days": p.days, "days_rounded": p.days_rounded,
                                            "baseline": p.baseline, "mde_relative": p.mde_relative, "daily_traffic": p.daily_traffic},
            "query": out.get("query"), "error": out.get("error")}


# --- install ------------------------------------------------------------------------------------------

def _state() -> str:
    t = str(int(time.time()))
    return t + "." + hmac.new(STATE_SECRET, t.encode(), hashlib.sha256).hexdigest()[:32]


def _state_ok(s: str) -> bool:
    try:
        t, sig = s.split(".")
        return hmac.compare_digest(sig, hmac.new(STATE_SECRET, t.encode(), hashlib.sha256).hexdigest()[:32]) and time.time() - int(t) < 900
    except ValueError:
        return False


@app.get("/install", include_in_schema=False)
def install(request: Request):
    if not linear.client_id():
        return HTMLResponse(_page("Not set up yet", "Add <code>LINEAR_CLIENT_ID</code> and <code>LINEAR_CLIENT_SECRET</code> on Render first."), 400)
    return RedirectResponse(linear.authorize_url(f"{_base(request)}/oauth/callback", _state()))


@app.get("/oauth/callback", include_in_schema=False)
def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse(_page("Install cancelled", f"Linear said: {error}"), 400)
    if not code or not _state_ok(state):
        return HTMLResponse(_page("That link expired", "Start again from the <a href='/'>home page</a>."), 400)
    try:
        me = linear.exchange_code(code, f"{_base(request)}/oauth/callback")
    except Exception as e:  # noqa: BLE001
        log.warning("install_failed %s", e)
        return HTMLResponse(_page("Install failed", "Linear didn't accept the code. Check the callback URL in the Linear app settings "
                                  "matches exactly, then try again."), 400)
    org = (me.get("organization") or {}).get("name", "your workspace")
    name = (me.get("viewer") or {}).get("name", "the agent")
    return HTMLResponse(_page("Installed", f"<b>{name}</b> is installed in <b>{org}</b>. Open any issue, type <code>@{name}</code> "
                                           "in a comment, and ask it to plan the test."))


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>{title}</title>"
            "<body style=\"font:17px/1.55 system-ui;max-width:36rem;margin:4rem auto;padding:0 1.2rem;color:#1b1f2a\">"
            f"<h1 style='font-size:1.8rem'>{title}</h1><p>{body}</p><p><a href='/'>Back</a></p>")


# --- the agent ----------------------------------------------------------------------------------------

@app.post("/webhooks/linear")
async def webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()
    ok, why = linear.verify(raw, request.headers.get("linear-signature"))
    if not ok:
        sec = linear.webhook_secret()
        log.warning("webhook_rejected reason=%s secret_len=%d secret_prefix_ok=%s secret_has_quote_or_space=%s sig_len=%d",
                    why, len(sec), sec.startswith("lin_wh_"), any(c in sec for c in "\"' =\n"),
                    len(request.headers.get("linear-signature") or ""))
        return JSONResponse(status_code=401, content={"error": why})
    payload = await request.json()
    if payload.get("type") != "AgentSessionEvent" and request.headers.get("linear-event") != "AgentSessionEvent":
        return {"ok": True, "ignored": payload.get("type")}
    delivery = request.headers.get("linear-delivery") or f"{(payload.get('agentSession') or {}).get('id')}:{payload.get('action')}:" \
                                                           f"{(payload.get('agentActivity') or {}).get('id')}"
    if not seen.first_time(delivery):
        return {"ok": True, "duplicate": True}
    background.add_task(handle, payload)  # reply to Linear now; the work happens after
    return {"ok": True}


def _issue_text(payload: dict) -> str:
    if payload.get("promptContext"):
        return payload["promptContext"]
    issue = (payload.get("agentSession") or {}).get("issue") or {}
    comment = (payload.get("agentSession") or {}).get("comment") or {}
    if not (issue.get("title") or issue.get("description") or comment.get("body")):
        return ""
    return "\n".join(x for x in [f"<title>{issue.get('title', '')}</title>", issue.get("description") or "", comment.get("body") or ""] if x)


def _fetch_issue(session_id: str) -> str:
    """After a restart the session's issue isn't in memory: ask Linear for it."""
    try:
        d = linear.graphql("query($id: String!) { agentSession(id: $id) { issue { title description } } }", {"id": session_id})
        issue = (d.get("agentSession") or {}).get("issue") or {}
        return f"<title>{issue.get('title', '')}</title>\n{issue.get('description') or ''}"
    except Exception as e:  # noqa: BLE001
        log.warning("fetch_issue_failed %s", e)
        return ""


def handle(payload: dict) -> None:
    session = payload.get("agentSession") or {}
    sid = session.get("id")
    if not sid:
        return
    act = payload.get("action")
    try:
        if act == "created":
            linear.thought(sid, "Reading the issue and sizing the test…")  # within 10 seconds, so Linear knows it's working
            sessions[sid] = {"context": _issue_text(payload), "extra": ""}
        elif act == "prompted":
            activity = payload.get("agentActivity") or {}
            if activity.get("signal") == "stop":
                linear.response(sid, "Stopped.")
                return
            body = ((activity.get("content") or {}).get("body") or activity.get("body") or "").strip()
            s = sessions.setdefault(sid, {"context": _issue_text(payload) or _fetch_issue(sid), "extra": ""})
            s["extra"] = (s["extra"] + "\n" + body).strip()
            linear.thought(sid, "Recalculating with your numbers…")
        else:
            return
        s = sessions[sid]
        found = design.numbers(s["context"] + "\n" + s["extra"])
        linear.action(sid, "Reading numbers", "baseline, lift, traffic",
                      ", ".join(f"{k} = {v}" for k, v in found.items() if k != "mde_was_absolute") or "none stated, using defaults")
        out = design.build(s["context"], s["extra"])
        if out.get("plan"):
            p = out["plan"]
            linear.action(sid, "Calculated sample size", f"{p.variants} variants",
                          f"{p.per_variant:,} users per variant" + (f", {p.days_rounded} days" if p.days_rounded else ""))
        linear.response(sid, out["markdown"])
    except Exception as e:  # noqa: BLE001
        log.exception("agent_failed session=%s", sid)
        reason = re.sub(r"[\n`]", " ", str(e))[:200]
        try:
            linear.error(sid, f"Something went wrong while planning this test: {reason}")
        except Exception:  # noqa: BLE001
            pass
