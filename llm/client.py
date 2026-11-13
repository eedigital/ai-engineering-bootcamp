"""One LLM client for every week of the bootcamp.

Every provider here speaks the OpenAI-compatible /chat/completions API, so
switching between Gemini, Groq and a local Ollama model is one env var.

    LLM_PROVIDERS=gemini,groq,ollama   # tried in order; next one on rate limit / outage

The "fake" provider returns canned answers so tests and CI never need a key.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

log = logging.getLogger("llm")


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    api_key_env: str | None  # None = no key needed (Ollama)


def _providers() -> dict[str, Provider]:
    # Read at call time so env changes (and tests) take effect without a restart.
    return {
        "gemini": Provider(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            "GEMINI_API_KEY",
        ),
        "groq": Provider(
            "groq",
            "https://api.groq.com/openai/v1",
            os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            "GROQ_API_KEY",
        ),
        "ollama": Provider(
            "ollama",
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
            None,
        ),
    }


class LLMError(Exception):
    """Every provider failed. The message lists why each one failed."""


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int = 1
    errors: list[str] = field(default_factory=list)


# --- fake provider (tests / CI) --------------------------------------------

FakeHandler = Callable[[list[dict]], str]
_fake_handler: FakeHandler | None = None


def set_fake_handler(handler: FakeHandler | None) -> None:
    """Tests register a function messages -> reply text."""
    global _fake_handler
    _fake_handler = handler


def _call_fake(messages: list[dict]) -> LLMResult:
    if _fake_handler is None:
        raise LLMError("fake provider selected but no handler set")
    start = time.perf_counter()
    text = _fake_handler(messages)
    return LLMResult(text, "fake", "fake", (time.perf_counter() - start) * 1000)


# --- real providers --------------------------------------------------------

RETRYABLE = {408, 429, 500, 502, 503, 504}
BUSY = {429, 503}  # "rate limited" / "high demand": skip straight to a backup if there is one


def _error_detail(r: httpx.Response) -> str:
    """The provider's own error message (e.g. 'API key not valid'), shortened."""
    try:
        body = r.json()
        if isinstance(body, list) and body:
            body = body[0]
        err = body.get("error", body)
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
    except Exception:
        msg = r.text
    return f"({msg.strip()[:160]})" if msg and msg.strip() else ""


def _call_provider(
    p: Provider,
    messages: list[dict],
    *,
    json_mode: bool,
    temperature: float,
    timeout_s: float,
    max_retries: int,
    has_fallback: bool = False,
) -> LLMResult:
    headers = {"Content-Type": "application/json"}
    if p.api_key_env:
        key = os.getenv(p.api_key_env)
        if not key:
            raise LLMError(f"{p.name}: {p.api_key_env} is not set")
        headers["Authorization"] = f"Bearer {key}"

    body: dict = {"model": p.model, "messages": messages, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    errors: list[str] = []
    for attempt in range(1, max_retries + 2):
        start = time.perf_counter()
        try:
            r = httpx.post(
                f"{p.base_url}/chat/completions", headers=headers, json=body, timeout=timeout_s
            )
        except httpx.HTTPError as e:  # network error / timeout
            errors.append(f"{p.name} attempt {attempt}: {type(e).__name__}")
        else:
            latency = (time.perf_counter() - start) * 1000
            if r.status_code == 200:
                data = r.json()
                usage = data.get("usage") or {}
                result = LLMResult(
                    text=data["choices"][0]["message"]["content"] or "",
                    provider=p.name,
                    model=p.model,
                    latency_ms=latency,
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    attempts=attempt,
                    errors=errors,
                )
                log.info(
                    "llm_call provider=%s model=%s latency_ms=%.0f in=%s out=%s attempts=%d",
                    p.name, p.model, latency, result.input_tokens, result.output_tokens, attempt,
                )
                return result
            errors.append(f"{p.name} attempt {attempt}: HTTP {r.status_code} {_error_detail(r)}".strip())
            if r.status_code not in RETRYABLE:
                break  # 400/401/403/404: retrying won't help
            if r.status_code in BUSY and has_fallback:
                break  # busy or rate limited: a backup answers faster than waiting
            if r.status_code == 429 and attempt > 1:
                break  # still rate limited after a backoff
        if attempt <= max_retries:
            time.sleep(min(2 ** (attempt - 1), 8))  # 1s, 2s, 4s, 8s
    raise LLMError("; ".join(errors))


def complete(
    messages: list[dict],
    *,
    json_mode: bool = False,
    temperature: float = 0.0,
    timeout_s: float = 30.0,
    max_retries: int = 2,
    providers: list[str] | None = None,
) -> LLMResult:
    """Send a chat to the first provider that answers.

    Providers come from the argument, else LLM_PROVIDERS (comma separated),
    else "gemini,groq,ollama".
    """
    order = providers or [
        s.strip() for s in os.getenv("LLM_PROVIDERS", "gemini,groq,ollama").split(",") if s.strip()
    ]
    table = _providers()
    failures: list[str] = []
    for i, name in enumerate(order):
        if name == "fake":
            return _call_fake(messages)
        p = table.get(name)
        if p is None:
            failures.append(f"unknown provider '{name}'")
            continue
        try:
            return _call_provider(
                p, messages, json_mode=json_mode, temperature=temperature,
                timeout_s=timeout_s, max_retries=max_retries,
                has_fallback=i < len(order) - 1,  # only the last provider waits and retries
            )
        except LLMError as e:
            log.warning("provider failed, trying next: %s", e)
            failures.append(str(e))
    raise LLMError(" | ".join(failures) or "no providers configured")


def parse_json(text: str) -> dict:
    """Parse model output as JSON, tolerating ```json fences some models add."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return json.loads(t)
