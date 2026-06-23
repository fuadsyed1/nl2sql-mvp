"""
llm/providers/ollama_provider.py

Phase 6.5, step 2 — native Ollama provider adapter.

Implements the LLMProvider interface against Ollama's native endpoints:
  POST /api/generate   (single prompt)
  POST /api/chat       (message list)
  GET  /api/tags       (health + model catalog)

Behavior preserves the current SpiderSQL setup: it sends the same
{model, prompt, stream:false, options:{temperature, num_predict}} shape, mapping
`temperature`, `num_predict`, and `think` from per-call options (falling back to
the LLMConfig defaults). It never raises raw `requests` exceptions — transport
and protocol failures are converted into typed provider errors.

This module is one adapter only: no provider selection, no extractor logic, no
SQL pipeline involvement.
"""

import requests

from ..base import LLMProvider, GenerationResult, ChatResult, Message
from ..config import LLMConfig
from ..errors import (
    ProviderError,
    ProviderUnavailable,
    ProviderAuthError,
    ProviderQuotaError,
)

__all__ = ["OllamaProvider"]


class OllamaProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        self.config = config

    # -- request helpers -----------------------------------------------------
    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _resolve(self, options):
        """Map per-call options over the config defaults."""
        options = options or {}
        ollama_options = {
            "temperature": options.get("temperature", self.config.temperature),
            "num_predict": options.get("num_predict", self.config.num_predict),
        }
        think = options.get("think", self.config.think)
        return ollama_options, think

    def _check_status(self, resp):
        status = resp.status_code
        if status in (401, 403):
            raise ProviderAuthError(f"authentication failed (HTTP {status})")
        if status == 429:
            raise ProviderQuotaError("rate limit / quota exceeded (HTTP 429)")
        if status >= 500:
            raise ProviderUnavailable(f"backend error (HTTP {status})")
        if status >= 400:
            raise ProviderError(f"request failed (HTTP {status})")

    def _parse_json(self, resp):
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("malformed JSON response from provider") from exc

    def _post(self, path, payload):
        url = self.config.base_url + path
        try:
            resp = requests.post(
                url, json=payload, headers=self._headers(),
                timeout=self.config.timeout_seconds, verify=self.config.verify_ssl,
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderUnavailable(f"timeout contacting {url}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUnavailable(f"cannot connect to {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderError(f"request to {url} failed: {exc}") from exc
        self._check_status(resp)
        return self._parse_json(resp)

    def _get(self, path):
        url = self.config.base_url + path
        try:
            resp = requests.get(
                url, headers=self._headers(),
                timeout=self.config.timeout_seconds, verify=self.config.verify_ssl,
            )
        except requests.exceptions.Timeout as exc:
            raise ProviderUnavailable(f"timeout contacting {url}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ProviderUnavailable(f"cannot connect to {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderError(f"request to {url} failed: {exc}") from exc
        self._check_status(resp)
        return self._parse_json(resp)

    # -- interface -----------------------------------------------------------
    def generate(self, prompt: str, options: dict | None = None) -> GenerationResult:
        ollama_options, think = self._resolve(options)
        payload = {
            "model": self.config.model_name,
            "prompt": prompt,
            "stream": False,
            "think": think,
            "options": ollama_options,
        }
        data = self._post("/api/generate", payload)
        if not isinstance(data, dict):
            return GenerationResult(text="", model=self.config.model_name, raw={})
        return GenerationResult(
            text=data.get("response", "") or "",
            model=data.get("model") or self.config.model_name,
            raw=data,
        )

    def chat(self, messages, options: dict | None = None) -> ChatResult:
        ollama_options, think = self._resolve(options)
        wire_messages = []
        for m in messages or []:
            if isinstance(m, Message):
                wire_messages.append({"role": m.role, "content": m.content})
            elif isinstance(m, dict):
                wire_messages.append({"role": m.get("role"), "content": m.get("content")})
        payload = {
            "model": self.config.model_name,
            "messages": wire_messages,
            "stream": False,
            "think": think,
            "options": ollama_options,
        }
        data = self._post("/api/chat", payload)
        if not isinstance(data, dict):
            return ChatResult(text="", model=self.config.model_name, raw={})
        message = data.get("message") or {}
        text = message.get("content", "") if isinstance(message, dict) else ""
        return ChatResult(
            text=text or "",
            model=data.get("model") or self.config.model_name,
            raw=data,
        )

    def health_check(self) -> bool:
        try:
            self._get("/api/tags")
            return True
        except ProviderError:
            return False
        except Exception:
            return False

    def list_models(self) -> list[str]:
        data = self._get("/api/tags")
        models = data.get("models", []) if isinstance(data, dict) else []
        names = []
        for m in models:
            if isinstance(m, dict) and m.get("name"):
                names.append(m["name"])
            elif isinstance(m, str):
                names.append(m)
        return names