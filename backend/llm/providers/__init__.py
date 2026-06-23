"""
llm.providers — concrete LLM provider adapters.

Step 2 ships the native Ollama adapter. MindRouter and OpenAI-compatible
adapters are added in later steps.
"""

from .ollama_provider import OllamaProvider

__all__ = ["OllamaProvider"]