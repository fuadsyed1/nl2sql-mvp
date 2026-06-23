"""
llm/providers/mindrouter_provider.py

Phase 6.5, step 3 — MindRouter provider adapter (Ollama-compatible mode).

MindRouter exposes an Ollama-compatible API (POST /api/generate, POST /api/chat,
GET /api/tags) in front of a pool of remote backends — including
university-hosted models on the AI4RA/RCDS GPU cluster. Because SpiderSQL already
speaks Ollama-style generate calls, this adapter extends OllamaProvider and only
adds what MindRouter requires:

  * a mandatory API key sent as `Authorization: Bearer <LLM_API_KEY>`
    (the parent already attaches this header when api_key is set; here it is
    required, and a missing key raises ProviderAuthError BEFORE any HTTP call),
  * the configured base URL pointing at the MindRouter gateway, and
  * the exact LLM_MODEL_NAME (MindRouter does not alias/fuzzy-match names).

Selecting this provider means inference runs remotely: this machine only sends
HTTP requests and receives responses; no model executes locally.

All request shaping, option mapping (temperature / num_predict / think),
response parsing, and typed-error conversion are inherited from OllamaProvider.
"""

from .ollama_provider import OllamaProvider
from ..base import GenerationResult, ChatResult
from ..errors import ProviderAuthError

__all__ = ["MindRouterProvider"]


class MindRouterProvider(OllamaProvider):
    """MindRouter gateway via its Ollama-compatible endpoints."""

    def _require_key(self):
        """MindRouter requires authentication. Fail fast, before any request."""
        if not self.config.api_key:
            raise ProviderAuthError(
                "MindRouter requires an API key (set LLM_API_KEY)"
            )

    def generate(self, prompt: str, options: dict | None = None) -> GenerationResult:
        self._require_key()
        return super().generate(prompt, options)

    def chat(self, messages, options: dict | None = None) -> ChatResult:
        self._require_key()
        return super().chat(messages, options)

    def list_models(self) -> list[str]:
        self._require_key()
        return super().list_models()

    def health_check(self) -> bool:
        # Without a key MindRouter cannot be reached as authenticated; report
        # unhealthy rather than raising (health_check never raises).
        if not self.config.api_key:
            return False
        return super().health_check()