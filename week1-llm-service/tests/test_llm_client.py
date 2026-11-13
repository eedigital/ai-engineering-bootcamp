"""The shared llm/ client: fallback and retry behaviour, with HTTP faked out."""


import httpx
import pytest

from llm import LLMError, complete
from llm import client as llm_client

OK_BODY = {"choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}
BUSY_BODY = {"error": {"message": "This model is currently experiencing high demand."}}


@pytest.fixture
def fake_http(monkeypatch):
    """Script replies per provider host; records which hosts were called, in order."""
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: sleeps.append(s))
    calls: list[str] = []
    sleeps: list[float] = []
    script: dict[str, list[tuple[int, dict]]] = {}

    def post(url, **kwargs):
        host = "gemini" if "googleapis" in url else "groq"
        calls.append(host)
        status, body = script[host].pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_client.httpx, "post", post)
    return script, calls, sleeps


def test_busy_provider_hands_over_immediately(fake_http):
    script, calls, sleeps = fake_http
    script["gemini"] = [(503, BUSY_BODY)]
    script["groq"] = [(200, OK_BODY)]
    result = complete([{"role": "user", "content": "hi"}], providers=["gemini", "groq"])
    assert result.provider == "groq"
    assert calls == ["gemini", "groq"]  # one try at Gemini, no retries
    assert sleeps == []  # and no waiting


def test_rate_limited_provider_hands_over_immediately(fake_http):
    script, calls, sleeps = fake_http
    script["gemini"] = [(429, {})]
    script["groq"] = [(200, OK_BODY)]
    assert complete([], providers=["gemini", "groq"]).provider == "groq"
    assert sleeps == []


def test_last_provider_still_retries_when_busy(fake_http):
    script, calls, sleeps = fake_http
    script["groq"] = [(503, BUSY_BODY), (200, OK_BODY)]
    result = complete([], providers=["groq"])
    assert result.provider == "groq" and result.attempts == 2
    assert sleeps == [1]


def test_missing_model_is_not_retried(fake_http):
    script, calls, sleeps = fake_http
    script["gemini"] = [(404, {"error": {"message": "model not found"}})]
    with pytest.raises(LLMError, match="model not found"):
        complete([], providers=["gemini"])
    assert calls == ["gemini"] and sleeps == []


def test_hanging_provider_hands_over_immediately(fake_http, monkeypatch):
    script, calls, sleeps = fake_http
    script["groq"] = [(200, OK_BODY)]
    real_post = llm_client.httpx.post

    def post(url, **kwargs):
        if "googleapis" in url:
            calls.append("gemini")
            raise httpx.ReadTimeout("no reply", request=httpx.Request("POST", url))
        return real_post(url, **kwargs)

    monkeypatch.setattr(llm_client.httpx, "post", post)
    assert complete([], providers=["gemini", "groq"]).provider == "groq"
    assert calls == ["gemini", "groq"] and sleeps == []
