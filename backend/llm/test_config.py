"""
test_config.py — offline test for Phase 6.5 step 1 (llm/config.py + base.py).

Runnable as a plain script (no server, no LLM, no network, no pytest):

    python test_config.py
"""

from .config import LLMConfig, load_from_env, DEFAULTS
from .base import Message, GenerationResult, ChatResult, LLMProvider


def test_defaults_preserve_local_ollama():
    cfg = load_from_env({})  # empty env -> all defaults
    assert isinstance(cfg, LLMConfig)
    assert cfg.provider == "ollama"
    assert cfg.base_url == "http://localhost:11434"
    assert cfg.api_key == ""
    assert cfg.model_name == "qwen3:1.7b"
    assert cfg.api_style == "ollama"
    assert cfg.timeout_seconds == 90
    assert cfg.num_predict == 700
    assert cfg.temperature == 0.0
    assert cfg.think is False
    assert cfg.verify_ssl is True
    # default = current behavior = model runs locally on this machine
    assert cfg.runs_model_locally is True and cfg.is_remote is False
    print("[1] defaults preserve local Ollama (qwen3:1.7b, local) -> OK")


def test_environment_overrides():
    env = {
        "LLM_PROVIDER": "mindrouter",
        "LLM_BASE_URL": "https://mindrouter.uidaho.edu/",
        "LLM_API_KEY": "mr2_abc123",
        "LLM_MODEL_NAME": "qwen3-32k:32b",
        "LLM_API_STYLE": "ollama",
        "LLM_TIMEOUT_SECONDS": "120",
        "LLM_NUM_PREDICT": "500",
        "LLM_TEMPERATURE": "0.7",
        "LLM_THINK": "true",
        "LLM_VERIFY_SSL": "false",
    }
    cfg = load_from_env(env)
    assert cfg.provider == "mindrouter"
    assert cfg.base_url == "https://mindrouter.uidaho.edu"   # trailing slash trimmed
    assert cfg.api_key == "mr2_abc123"
    assert cfg.model_name == "qwen3-32k:32b"
    assert cfg.api_style == "ollama"
    assert cfg.timeout_seconds == 120
    assert cfg.num_predict == 500
    assert cfg.temperature == 0.7
    assert cfg.think is True
    assert cfg.verify_ssl is False
    print("[2] environment overrides applied -> OK")


def test_bool_parsing():
    for truthy in ("true", "True", "1", "yes", "on", "Y"):
        assert load_from_env({"LLM_THINK": truthy}).think is True
    for falsy in ("false", "False", "0", "no", "off", "n"):
        assert load_from_env({"LLM_THINK": falsy}).think is False
    # garbage -> default (False)
    assert load_from_env({"LLM_THINK": "maybe"}).think is False
    # verify_ssl default True, overridable
    assert load_from_env({"LLM_VERIFY_SSL": "0"}).verify_ssl is False
    assert load_from_env({}).verify_ssl is True
    print("[3] bool parsing (true/false/1/0/yes/no + fallback) -> OK")


def test_numeric_parsing():
    cfg = load_from_env({"LLM_TIMEOUT_SECONDS": "30", "LLM_NUM_PREDICT": "256", "LLM_TEMPERATURE": "0.2"})
    assert cfg.timeout_seconds == 30 and isinstance(cfg.timeout_seconds, int)
    assert cfg.num_predict == 256 and isinstance(cfg.num_predict, int)
    assert cfg.temperature == 0.2 and isinstance(cfg.temperature, float)
    # invalid numerics fall back to defaults
    bad = load_from_env({"LLM_TIMEOUT_SECONDS": "abc", "LLM_NUM_PREDICT": "x", "LLM_TEMPERATURE": "y"})
    assert bad.timeout_seconds == 90 and bad.num_predict == 700 and bad.temperature == 0.0
    print("[4] numeric parsing (int/float + fallback on garbage) -> OK")


def test_mindrouter_config_example():
    env = {
        "LLM_PROVIDER": "mindrouter",
        "LLM_BASE_URL": "https://mindrouter.uidaho.edu",
        "LLM_API_KEY": "mr2_example_key",
        "LLM_MODEL_NAME": "deepseek-r1:70b",
        "LLM_API_STYLE": "ollama",   # decision: Ollama-compatible mode
    }
    cfg = load_from_env(env)
    assert cfg.provider == "mindrouter"
    assert cfg.api_style == "ollama"
    assert cfg.base_url.startswith("https://")
    assert cfg.api_key == "mr2_example_key"
    assert cfg.model_name == "deepseek-r1:70b"
    print("[5] MindRouter config example (Ollama-compatible mode) -> OK")


def test_mindrouter_means_remote_not_local():
    # MindRouter -> inference is remote; the laptop only sends/receives.
    mr = load_from_env({"LLM_PROVIDER": "mindrouter",
                        "LLM_BASE_URL": "https://mindrouter.uidaho.edu",
                        "LLM_API_KEY": "mr2_x", "LLM_MODEL_NAME": "qwen3:32b"})
    assert mr.runs_model_locally is False, "MindRouter must not run a local model"
    assert mr.is_remote is True

    # default local Ollama -> model runs on this machine
    local = load_from_env({})
    assert local.runs_model_locally is True and local.is_remote is False

    # even Ollama pointed at a remote host is remote (no local execution)
    remote_ollama = load_from_env({"LLM_BASE_URL": "http://gpu-node.cluster:11434"})
    assert remote_ollama.runs_model_locally is False and remote_ollama.is_remote is True
    print("[6] MindRouter => remote inference, not local model execution -> OK")


def test_interface_is_abstract():
    # The interface cannot be instantiated directly (it is a contract only).
    try:
        LLMProvider()
        raise AssertionError("LLMProvider should be abstract")
    except TypeError:
        pass
    # result/message dataclasses construct as expected
    assert Message("user", "hi").role == "user"
    assert GenerationResult(text="{}").text == "{}"
    assert ChatResult(text="hi").text == "hi"
    print("[7] LLMProvider is abstract; result dataclasses construct -> OK")


def main():
    tests = [
        test_defaults_preserve_local_ollama,
        test_environment_overrides,
        test_bool_parsing,
        test_numeric_parsing,
        test_mindrouter_config_example,
        test_mindrouter_means_remote_not_local,
        test_interface_is_abstract,
    ]
    passed = 0
    for t in tests:
        t()
        passed += 1
    print(f"\nRESULT: {passed}/{len(tests)} passed — llm config foundation verified")


if __name__ == "__main__":
    main()