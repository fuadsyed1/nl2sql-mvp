"""
test_mindrouter_provider.py — offline test for Phase 6.5 step 3.

Mocked HTTP only (no real MindRouter call, no network). The shared HTTP seam
lives in ollama_provider (MindRouterProvider extends OllamaProvider), so we
patch `ollama_provider.requests`. Run as a package module:

    python -m llm.test_mindrouter_provider
"""

import requests as real_requests

from llm.config import load_from_env
from llm.base import Message
from llm.errors import (
    ProviderError, ProviderUnavailable, ProviderAuthError, ProviderQuotaError,
)
from llm.providers import ollama_provider          # shared HTTP seam to patch
from llm.providers.mindrouter_provider import MindRouterProvider

MR_ENV = {
    "LLM_PROVIDER": "mindrouter",
    "LLM_BASE_URL": "https://mindrouter.uidaho.edu",
    "LLM_API_KEY": "mr2_testkey",
    "LLM_MODEL_NAME": "qwen3:32b",
    "LLM_API_STYLE": "ollama",
}


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


def provider(env=None):
    return MindRouterProvider(load_from_env(env or MR_ENV))


# --- tests ------------------------------------------------------------------
def test_generate_endpoint_and_mapping():
    fake = install(lambda m, url, kw: FakeResp(200, {"response": "remote answer", "model": "qwen3:32b"}))
    r = provider().generate("hi")
    assert r.text == "remote answer" and r.model == "qwen3:32b"
    assert fake.calls[-1][1] == "https://mindrouter.uidaho.edu/api/generate"
    # exact model name used
    assert fake.calls[-1][2]["json"]["model"] == "qwen3:32b"
    print("[1] generate() endpoint + response mapping (remote) -> OK")


def test_bearer_header_included():
    fake = install(lambda m, url, kw: FakeResp(200, {"response": "x"}))
    provider().generate("p")
    headers = fake.calls[-1][2]["headers"]
    assert headers.get("Authorization") == "Bearer mr2_testkey", headers
    print("[2] Authorization: Bearer header included -> OK")


def test_missing_key_raises_before_http():
    env = dict(MR_ENV); env["LLM_API_KEY"] = ""
    fake = install(lambda m, url, kw: FakeResp(200, {"response": "x"}))
    try:
        provider(env).generate("p")
        raise AssertionError("expected ProviderAuthError")
    except ProviderAuthError:
        pass
    assert fake.calls == [], "no HTTP call should be made without a key"
    # chat and list_models also guard
    for call in (lambda: provider(env).chat([Message("user", "h")]),
                 lambda: provider(env).list_models()):
        try:
            call()
            raise AssertionError("expected ProviderAuthError")
        except ProviderAuthError:
            pass
    assert fake.calls == []
    print("[3] missing API key -> ProviderAuthError before HTTP -> OK")


def test_chat_mapping():
    fake = install(lambda m, url, kw: FakeResp(200, {"message": {"role": "assistant", "content": "hello"}, "model": "qwen3:32b"}))
    r = provider().chat([Message("user", "hey")])
    assert r.text == "hello"
    assert fake.calls[-1][1].endswith("/api/chat")
    assert fake.calls[-1][2]["headers"]["Authorization"] == "Bearer mr2_testkey"
    print("[4] chat() response mapping (authed) -> OK")


def test_health_check():
    install(lambda m, url, kw: FakeResp(200, {"models": []}))
    assert provider().health_check() is True
    # no key -> False, no HTTP
    env = dict(MR_ENV); env["LLM_API_KEY"] = ""
    fake = install(lambda m, url, kw: FakeResp(200, {"models": []}))
    assert provider(env).health_check() is False and fake.calls == []
    print("[5] health_check() (authed up=True; no key=False) -> OK")


def test_list_models():
    install(lambda m, url, kw: FakeResp(200, {"models": [{"name": "qwen3:32b"}, {"name": "deepseek-r1:70b"}]}))
    assert provider().list_models() == ["qwen3:32b", "deepseek-r1:70b"]
    assert ollama_provider.requests.calls[-1][1].endswith("/api/tags")
    print("[6] list_models() -> OK")


def test_transport_errors():
    def to(m, url, kw):
        raise real_requests.exceptions.Timeout("t")
    install(to)
    try:
        provider().generate("p"); raise AssertionError
    except ProviderUnavailable:
        pass

    def conn(m, url, kw):
        raise real_requests.exceptions.ConnectionError("c")
    install(conn)
    try:
        provider().generate("p"); raise AssertionError
    except ProviderUnavailable:
        pass

    install(lambda m, url, kw: FakeResp(503, text="down"))
    try:
        provider().generate("p"); raise AssertionError
    except ProviderUnavailable:
        pass
    print("[7] timeout/connection/5xx -> ProviderUnavailable -> OK")


def test_auth_and_quota_errors():
    for code in (401, 403):
        install(lambda m, url, kw, c=code: FakeResp(c, text="no"))
        try:
            provider().generate("p"); raise AssertionError
        except ProviderAuthError:
            pass
    install(lambda m, url, kw: FakeResp(429, text="slow down"))
    try:
        provider().generate("p"); raise AssertionError
    except ProviderQuotaError:
        pass
    print("[8] 401/403 -> ProviderAuthError; 429 -> ProviderQuotaError -> OK")


def test_malformed_json():
    install(lambda m, url, kw: FakeResp(200, raise_json=True))
    try:
        provider().generate("p"); raise AssertionError
    except ProviderError:
        pass
    print("[9] malformed JSON -> ProviderError -> OK")


def test_option_mapping():
    fake = install(lambda m, url, kw: FakeResp(200, {"response": "x"}))
    provider().generate("p", options={"temperature": 0.3, "num_predict": 128, "think": True})
    payload = fake.calls[-1][2]["json"]
    assert payload["options"] == {"temperature": 0.3, "num_predict": 128}
    assert payload["think"] is True and payload["model"] == "qwen3:32b"
    print("[10] option mapping (temperature/num_predict/think) -> OK")


def test_config_is_remote():
    cfg = load_from_env(MR_ENV)
    assert cfg.provider == "mindrouter"
    assert cfg.runs_model_locally is False and cfg.is_remote is True
    print("[11] config => remote inference, not local model execution -> OK")


def main():
    original = ollama_provider.requests
    tests = [
        test_generate_endpoint_and_mapping,
        test_bearer_header_included,
        test_missing_key_raises_before_http,
        test_chat_mapping,
        test_health_check,
        test_list_models,
        test_transport_errors,
        test_auth_and_quota_errors,
        test_malformed_json,
        test_option_mapping,
        test_config_is_remote,
    ]
    try:
        passed = 0
        for t in tests:
            t()
            passed += 1
        print(f"\nRESULT: {passed}/{len(tests)} passed — MindRouterProvider verified")
    finally:
        ollama_provider.requests = original


if __name__ == "__main__":
    main()