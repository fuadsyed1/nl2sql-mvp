"""
llm/errors.py

Phase 6.5, step 2 — typed provider exceptions.

Adapters convert raw transport/protocol failures into these typed errors so the
rest of SpiderSQL never sees a `requests` exception. All inherit from
ProviderError, so a caller can catch the base class to handle any provider
failure, or a specific subclass to handle a particular condition.
"""

__all__ = [
    "ProviderError",
    "ProviderUnavailable",
    "ProviderAuthError",
    "ProviderQuotaError",
]


class ProviderError(Exception):
    """Base class for all provider failures."""


class ProviderUnavailable(ProviderError):
    """The backend could not be reached (timeout, connection error, 5xx)."""


class ProviderAuthError(ProviderError):
    """Authentication/authorization failed (HTTP 401/403)."""


class ProviderQuotaError(ProviderError):
    """Rate limit or token/quota budget exceeded (HTTP 429)."""