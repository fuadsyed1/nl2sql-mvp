"""
test_ollama_provider.py — offline test for Phase 6.5 step 2.

Uses mocked HTTP only (the provider's `requests` module is swapped for a fake);
no server, no Ollama, no network, no pytest. Run as a package module:

    python -m llm.test_ollama_provider
"""

import requests as real_requests

from llm.config import load_from_env
from llm.base import Message
from llm.errors import (
    ProviderError, ProviderUnavailable, ProviderAuthError, ProviderQuotaError,
)
from llm.providers import ollama_provider
from llm.providers.ollama_provider import OllamaProvider


# --- fake HTTP plumbing -----------------------------------------------------
class FakeResp:
    def __init__(self, status=200, json_data=None, text="OK", raise_json=False):
        self.status_code = status
        self._json = json_data
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("bad json")
        return self._json


class FakeRequests:
    """Stands in for the `requests` module inside ollama_provider."""
    exceptions = real_requests.exceptions

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.handler("POST", url, kw)

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self.handler("GET", url, kw)


def install(handler):
    fake = FakeRequests(handler)
    ollama_provider.requests = fake
    return fake


def make_provider(env=None):
    return OllamaProvider(load_from_env(env or {}))


# --- tests ------------------------------------------------------------------
def test_generate_response_mapping():
    fake = install(lambda m, url, kw: FakeResp(200, {"response": "hello world", "model": "qwen3:1.7b"}))
    r = make_provider().generate("say hi")
    assert r.text == "hello world"
    assert r.model == "qwen3:1.7b"
    assert r.raw["response"] == "hello world"
    # correct endpoint
    assert fake.calls[-1][1] == "http://localhost:11434/api/generate"
    print("[1] generate() response mapping -> OK")


def test_option_mapping():
    fake = install(lambda m, url, kw: FakeResp(200, {"response": "x"}))
    make_provider().generate("p", options={"temperature": 0.5, "num_predict": 256, "think": True})
    payload = fake.calls[-1][2]["json"]
    assert payload["model"] == "qwen3:1.7b"
    assert payload["stream"] is False
    assert payload["think"] is True
    assert payload["options"] == {"temperature": 0.5, "num_predict": 256}
    # defaults applied when options omitted
    install(lambda m, url, kw: FakeResp(200, {"response": "x"}))
    make_provider().generate("p")
    dpayload = ollama_provider.requests.calls[-1][2]["json"]
    assert dpayload["options"] == {"temperature": 0.0, "num_predict": 700} and dpayload["think"] is False
    print("[2] option mapping (temperature/num_predict/think + defaults) -> OK")


def test_chat_response_mapping():
    fake = install(lambda m, url, kw: FakeResp(200, {"message": {"role": "assistant", "content": "hi there"}, "model": "m"}))
    r = make_provider().chat([Message("user", "yo")])
    assert r.text == "hi there" and r.model == "m"
    assert fake.calls[-1][1].endswith("/api/chat")
    sent = fake.calls[-1][2]["json"]["messages"]
    assert sent == [{"role": "user", "content": "yo"}]
    print("[3] chat() response mapping -> OK")


def test_health_check():
    install(lambda m, url, kw: FakeResp(200, {"models": []}))
    assert make_provider().health_check() is True

    def raise_timeout(m, url, kw):
        raise real_requests.exceptions.Timeout("timed out")
    install(raise_timeout)
    assert make_provider().health_check() is False    # never raises
    print("[4] health_check() (up=True, unreachable=False) -> OK")


def test_list_models():
    install(lambda m, url, kw: FakeResp(200, {"models": [{"name": "qwen3:1.7b"}, {"name": "llama3:8b"}]}))
    assert make_provider().list_models() == ["qwen3:1.7b", "llama3:8b"]
    print("[5] list_models() -> OK")


def test_timeout_maps_to_unavailable():
    def raise_timeout(m, url, kw):
        raise real_requests.exceptions.Timeout("timed out")
    install(raise_timeout)
    try:
        make_provider().generate("p")
        raise AssertionError("expected ProviderUnavailable")
    except ProviderUnavailable:
        pass
    # connection error too
    def raise_conn(m, url, kw):
        raise real_requests.exceptions.ConnectionError("refused")
    install(raise_conn)
    try:
        make_provider().generate("p")
        raise AssertionError("expected ProviderUnavailable")
    except ProviderUnavailable:
        pass
    print("[6] timeout/connection error -> ProviderUnavailable -> OK")


def test_401_maps_to_auth_error():
    install(lambda m, url, kw: FakeResp(401, text="unauthorized"))
    try:
        make_provider().generate("p")
        raise AssertionError("expected ProviderAuthError")
    except ProviderAuthError:
        pass
    # 429 -> quota
    install(lambda m, url, kw: FakeResp(429, text="too many"))
    try:
        make_provider().generate("p")
        raise AssertionError("expected ProviderQuotaError")
    except ProviderQuotaError:
        pass
    print("[7] 401 -> ProviderAuthError; 429 -> ProviderQuotaError -> OK")


def test_malformed_response_handling():
    # bad JSON -> ProviderError
    install(lambda m, url, kw: FakeResp(200, raise_json=True))
    try:
        make_provider().generate("p")
        raise AssertionError("expected ProviderError on bad JSON")
    except ProviderError:
        pass
    # valid JSON missing 'response' -> graceful empty text (preserves current behavior)
    install(lambda m, url, kw: FakeResp(200, {"model": "m"}))
    r = make_provider().generate("p")
    assert r.text == "" and r.model == "m"
    print("[8] malformed JSON -> ProviderError; missing key -> empty text -> OK")


def main():
    original = ollama_provider.requests
    tests = [
        test_generate_response_mapping,
        test_option_mapping,
        test_chat_response_mapping,
        test_health_check,
        test_list_models,
        test_timeout_maps_to_unavailable,
        test_401_maps_to_auth_error,
        test_malformed_response_handling,
    ]
    try:
        passed = 0
        for t in tests:
            t()
            passed += 1
        print(f"\nRESULT: {passed}/{len(tests)} passed — OllamaProvider verified")
    finally:
        ollama_provider.requests = original


if __name__ == "__main__":
    main()