"""
test_factory.py — offline test for Phase 6.5 step 4 (llm/factory.py).

No network, no real provider calls — only construction/selection is exercised.
Run as a package module:

    python -m llm.test_factory
"""

import os

from llm import get_provider, reset_provider_cache
from llm.errors import ProviderError
from llm.providers.ollama_provider import OllamaProvider
from llm.providers.mindrouter_provider import MindRouterProvider

LLM_KEYS = [
    "LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL_NAME",
    "LLM_API_STYLE", "LLM_TIMEOUT_SECONDS", "LLM_NUM_PREDICT",
    "LLM_TEMPERATURE", "LLM_THINK", "LLM_VERIFY_SSL",
]


def configure(**kw):
    """Reset LLM_* env to exactly `kw`, then clear the provider cache."""
    for k in LLM_KEYS:
        os.environ.pop(k, None)
    for k, v in kw.items():
        os.environ[k] = v
    reset_provider_cache()


def mindrouter_env():
    return {
        "LLM_PROVIDER": "mindrouter",
        "LLM_BASE_URL": "https://mindrouter.uidaho.edu",
        "LLM_API_KEY": "mr2_testkey",
        "LLM_MODEL_NAME": "qwen3:32b",
        "LLM_API_STYLE": "ollama",
    }


def test_default_is_ollama():
    configure()  # no LLM_PROVIDER -> defaults
    p = get_provider()
    assert isinstance(p, OllamaProvider)
    assert p.config.provider == "ollama"
    print("[1] default provider is OllamaProvider -> OK")


def test_mindrouter_selected():
    configure(**mindrouter_env())
    p = get_provider()
    assert isinstance(p, MindRouterProvider)
    assert p.config.provider == "mindrouter"
    print("[2] LLM_PROVIDER=mindrouter -> MindRouterProvider -> OK")


def test_unknown_provider_raises():
    configure(LLM_PROVIDER="banana")
    try:
        get_provider()
        raise AssertionError("expected ProviderError")
    except ProviderError as exc:
        assert "banana" in str(exc) and "supported" in str(exc)
    print("[3] unknown provider -> ProviderError (clear message) -> OK")


def test_singleton_cache():
    configure()
    a = get_provider()
    b = get_provider()
    assert a is b, "cached provider must be the same instance"
    # changing env WITHOUT reset keeps the cached provider (restart-required)
    os.environ["LLM_PROVIDER"] = "mindrouter"
    c = get_provider()
    assert c is a, "provider change must not take effect without restart/reset"
    print("[4] singleton cache returns same object (restart-required) -> OK")


def test_reset_creates_new_object():
    configure()
    a = get_provider()
    reset_provider_cache()
    b = get_provider()
    assert a is not b, "reset must rebuild the provider"
    assert isinstance(b, OllamaProvider)
    print("[5] reset_provider_cache() creates a new object -> OK")


def test_mindrouter_is_remote():
    configure(**mindrouter_env())
    p = get_provider()
    assert p.config.runs_model_locally is False and p.config.is_remote is True
    print("[6] MindRouter via factory => remote inference, not local -> OK")


def main():
    # snapshot env to restore afterwards
    snapshot = {k: os.environ.get(k) for k in LLM_KEYS}
    tests = [
        test_default_is_ollama,
        test_mindrouter_selected,
        test_unknown_provider_raises,
        test_singleton_cache,
        test_reset_creates_new_object,
        test_mindrouter_is_remote,
    ]
    try:
        passed = 0
        for t in tests:
            t()
            passed += 1
        print(f"\nRESULT: {passed}/{len(tests)} passed — factory verified")
    finally:
        reset_provider_cache()
        for k, v in snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    main()