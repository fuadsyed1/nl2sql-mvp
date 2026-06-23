"""
llm.providers — concrete LLM provider adapters.

Step 2 shipped the native Ollama adapter; step 3 adds the MindRouter adapter
(Ollama-compatible mode). An OpenAI-compatible adapter may follow later.
"""

from .ollama_provider import OllamaProvider
from .mindrouter_provider import MindRouterProvider

__all__ = ["OllamaProvider", "MindRouterProvider"]