"""
llm/factory.py

Phase 6.5, step 4 — the provider factory.

get_provider() reads the configuration once (from the environment) and returns
the LLMProvider implementation selected by LLM_PROVIDER, caching it as a
process-wide singleton. Because the provider is built once and cached, changing
providers requires a server restart — which matches how the rest of SpiderSQL
treats configuration.

reset_provider_cache() exists only for tests, to force a fresh build after the
environment changes within a single process.

This module selects and constructs providers; it makes no network calls and
contains no extractor/SQL logic.
"""

from .config import load_from_env
from .errors import ProviderError
from .providers import OllamaProvider, MindRouterProvider

__all__ = ["get_provider", "reset_provider_cache"]

# provider key (LLM_PROVIDER) -> adapter class
_PROVIDERS = {
    "ollama": OllamaProvider,
    "mindrouter": MindRouterProvider,
}

_cached_provider = None


def get_provider():
    """Return the configured LLMProvider (cached process-wide).

    Builds the provider from the current environment on first call. Raises
    ProviderError for an unknown LLM_PROVIDER. Subsequent calls return the same
    instance until reset_provider_cache() is called (or the process restarts).
    """
    global _cached_provider
    if _cached_provider is not None:
        return _cached_provider

    config = load_from_env()
    provider_cls = _PROVIDERS.get(config.provider)
    if provider_cls is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ProviderError(
            f"unknown LLM_PROVIDER '{config.provider}'; supported: {supported}"
        )

    _cached_provider = provider_cls(config)
    return _cached_provider


def reset_provider_cache():
    """Clear the cached provider. For tests only — production switches providers
    via a config change + restart, not at runtime."""
    global _cached_provider
    _cached_provider = None