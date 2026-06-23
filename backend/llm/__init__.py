"""
llm — SpiderSQL LLM provider abstraction layer.

Exposes the interface + configuration foundation, the typed errors, and the
provider factory (get_provider / reset_provider_cache). Concrete providers live
in llm.providers.
"""

from .base import Message, GenerationResult, ChatResult, LLMProvider
from .config import LLMConfig, load_from_env, DEFAULTS
from .errors import (
    ProviderError,
    ProviderUnavailable,
    ProviderAuthError,
    ProviderQuotaError,
)
from .factory import get_provider, reset_provider_cache

__all__ = [
    "Message",
    "GenerationResult",
    "ChatResult",
    "LLMProvider",
    "LLMConfig",
    "load_from_env",
    "DEFAULTS",
    "ProviderError",
    "ProviderUnavailable",
    "ProviderAuthError",
    "ProviderQuotaError",
    "get_provider",
    "reset_provider_cache",
]