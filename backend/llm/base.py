"""
llm/base.py

Phase 6.5, step 1 — the LLM provider interface foundation.

Defines the canonical data shapes exchanged with any LLM backend and the
abstract LLMProvider interface that every concrete adapter (Ollama,
MindRouter, OpenAI-compatible, ...) will implement in a later step.

This module is pure contract: no HTTP, no provider selection, no configuration
reading, and no SpiderSQL business logic. It exists so the rest of the system
can depend on a stable interface rather than on a specific backend.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

__all__ = [
    "Message",
    "GenerationResult",
    "ChatResult",
    "LLMProvider",
]


@dataclass
class Message:
    """One chat message. `role` is typically 'system' | 'user' | 'assistant'."""
    role: str
    content: str


@dataclass
class GenerationResult:
    """Result of a single-prompt generation.

    `text` is the raw model output string — exactly what the SpiderSQL
    extractors parse today. `raw` carries the untouched provider response for
    debugging; `usage` is optional token accounting when a backend reports it.
    """
    text: str
    model: str | None = None
    raw: dict = field(default_factory=dict)
    usage: dict | None = None


@dataclass
class ChatResult:
    """Result of a multi-message chat completion. Same fields as
    GenerationResult; `text` is the assistant's reply content."""
    text: str
    model: str | None = None
    raw: dict = field(default_factory=dict)
    usage: dict | None = None


class LLMProvider(ABC):
    """Abstract interface every LLM backend adapter implements.

    Contract:
      * generate(prompt, options) -> GenerationResult
          Run a single prompt. `options` is an optional dict of generation
          parameters (e.g. temperature, num_predict, think); adapters map them
          to their backend's native fields. Returns a GenerationResult whose
          `.text` is the raw model output. Adapters must not raise transport
          exceptions to the caller; failures are surfaced as typed provider
          errors (defined in a later step).
      * chat(messages, options) -> ChatResult
          Run a list of Message objects as a chat completion.
      * health_check() -> bool
          Cheap liveness probe; returns True/False, never raises.
      * list_models() -> list[str]
          Model names the backend currently serves (for diagnostics and
          config validation).
    """

    @abstractmethod
    def generate(self, prompt: str, options: dict | None = None) -> GenerationResult:
        ...

    @abstractmethod
    def chat(self, messages: list[Message], options: dict | None = None) -> ChatResult:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        ...