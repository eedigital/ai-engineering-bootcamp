"""Run one prompt version on one test case and record what it cost: tokens, time and the result."""

from __future__ import annotations

import os

from llm import LLMError, complete

from . import checks
from .models import Case

# Which env var holds each provider's key. Ollama runs on a laptop, so it never shows on the live site.
KEYS = {"claude": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}


def estimate_tokens(text: str) -> int:
    """About 4 characters a token for English. Used only when a provider doesn't report usage."""
    return max(1, round(len(text) / 4))


def providers() -> list[dict]:
    """The providers this server can call, in LLM_PROVIDERS order, with their model names."""
    from llm.client import _providers  # read at call time, like the client does

    table = _providers()
    out = []
    for name in [s.strip() for s in os.getenv("LLM_PROVIDERS", "gemini,groq").split(",") if s.strip()]:
        if name == "fake":
            out.append({"name": "fake", "model": "fake"})
        elif name in KEYS and os.getenv(KEYS[name]):
            out.append({"name": name, "model": table[name].model})
        elif name == "ollama" and os.getenv("OLLAMA_BASE_URL"):
            out.append({"name": name, "model": table[name].model})
    return out


def run_case(prompt: str, case: Case, output: str, provider: str | None = None) -> dict:
    """One call, no fallback when a provider is named: a fair comparison needs every case on the same model."""
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": case.input}]
    base = {"case_id": case.id, "heldout": case.heldout}
    try:
        r = complete(messages, json_mode=output == "json", temperature=0.0,
                     providers=[provider] if provider else None, max_retries=1)
    except LLMError as e:
        return {**base, "passed": None, "error": str(e)[:300], "answer": "", "reasons": []}

    s = checks.score(r.text, case.expect)
    estimated = r.input_tokens is None or r.output_tokens is None
    return {
        **base,
        "passed": s.passed,
        "reasons": s.reasons,
        "answer": r.text[:2000],
        "provider": r.provider,
        "model": r.model,
        "latency_ms": round(r.latency_ms),
        "input_tokens": r.input_tokens if r.input_tokens is not None else estimate_tokens(prompt + case.input),
        "output_tokens": r.output_tokens if r.output_tokens is not None else estimate_tokens(r.text),
        "tokens_estimated": estimated,
        "error": None,
    }
