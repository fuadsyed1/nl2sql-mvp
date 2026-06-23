"""
llm — SpiderSQL LLM provider abstraction layer.

Step 1 exposes only the interface + configuration foundation. Concrete
providers (Ollama, MindRouter) and the factory are added in later steps.
"""

from .base import Message, GenerationResult, ChatResult, LLMProvider
from .config import LLMConfig, load_from_env, DEFAULTS

__all__ = [
    "Message",
    "GenerationResult",
    "ChatResult",
    "LLMProvider",
    "LLMConfig",
    "load_from_env",
    "DEFAULTS",
]