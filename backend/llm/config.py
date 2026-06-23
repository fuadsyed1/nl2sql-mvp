"""
llm/config.py

Phase 6.5, step 1 — LLM provider configuration.

Loads an immutable LLMConfig from environment variables so that switching
providers (local Ollama -> MindRouter -> university-hosted) is a .env change
with no SpiderSQL code change. The defaults reproduce today's behavior exactly:
local Ollama serving qwen3:1.7b.

This module reads configuration only. It does not construct providers, make
network calls, or run any model.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

__all__ = ["LLMConfig", "load_from_env", "DEFAULTS"]

# Defaults preserve the current local setup: SpiderSQL -> Ollama -> qwen3:1.7b.
DEFAULTS = {
    "LLM_PROVIDER": "ollama",
    "LLM_BASE_URL": "http://localhost:11434",
    "LLM_API_KEY": "",
    "LLM_MODEL_NAME": "qwen3:1.7b",
    "LLM_TIMEOUT_SECONDS": 90,
    "LLM_NUM_PREDICT": 700,
    "LLM_TEMPERATURE": 0.0,
    "LLM_THINK": False,
    "LLM_API_STYLE": "ollama",
    "LLM_VERIFY_SSL": True,
}

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}
_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}


def _as_bool(value, default):
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def _as_int(value, default):
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_float(value, default):
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model_name: str
    timeout_seconds: int
    num_predict: int
    temperature: float
    think: bool
    api_style: str
    verify_ssl: bool

    @property
    def runs_model_locally(self) -> bool:
        """True only when the model executes on this machine — i.e. the Ollama
        provider pointed at a local address. For MindRouter (or any non-local
        base URL) inference is remote: this laptop only sends/receives.
        """
        if self.provider != "ollama":
            return False
        host = (urlparse(self.base_url).hostname or "").lower()
        return host in _LOCAL_HOSTS

    @property
    def is_remote(self) -> bool:
        """True when inference happens off this machine."""
        return not self.runs_model_locally


def load_from_env(env=None) -> LLMConfig:
    """Build an LLMConfig from environment variables (os.environ by default).

    An explicit `env` dict may be passed for testing. Missing variables fall
    back to DEFAULTS, which reproduce the current local Ollama setup.
    """
    env = os.environ if env is None else env

    def get(name):
        value = env.get(name)
        return value if value not in (None, "") else None

    provider = (get("LLM_PROVIDER") or DEFAULTS["LLM_PROVIDER"]).strip().lower()
    api_style = (get("LLM_API_STYLE") or DEFAULTS["LLM_API_STYLE"]).strip().lower()
    base_url = (get("LLM_BASE_URL") or DEFAULTS["LLM_BASE_URL"]).strip().rstrip("/")
    # api_key may legitimately be empty for local Ollama; read raw (not via get()).
    api_key = (env.get("LLM_API_KEY") or DEFAULTS["LLM_API_KEY"]).strip()
    model_name = (get("LLM_MODEL_NAME") or DEFAULTS["LLM_MODEL_NAME"]).strip()

    return LLMConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        timeout_seconds=_as_int(get("LLM_TIMEOUT_SECONDS"), DEFAULTS["LLM_TIMEOUT_SECONDS"]),
        num_predict=_as_int(get("LLM_NUM_PREDICT"), DEFAULTS["LLM_NUM_PREDICT"]),
        temperature=_as_float(get("LLM_TEMPERATURE"), DEFAULTS["LLM_TEMPERATURE"]),
        think=_as_bool(get("LLM_THINK"), DEFAULTS["LLM_THINK"]),
        api_style=api_style,
        verify_ssl=_as_bool(get("LLM_VERIFY_SSL"), DEFAULTS["LLM_VERIFY_SSL"]),
    )