"""Thin wrapper around the official Groq SDK with friendly error mapping."""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator

# pyrefly: ignore[missing-import]
import groq

from app.config import Settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    """An error safe to show to the user, with an HTTP-ish status code."""

    def __init__(self, message: str, status_code: int = 502, code: str = "llm_error") -> None:
        super().__init__(message)
        self.message, self.status_code, self.code = message, status_code, code


def _map_error(exc: Exception, model: str) -> LLMError:
    if isinstance(exc, groq.AuthenticationError):
        return LLMError("Groq rejected the API key. Check GROQ_API_KEY in backend/.env.", 401, "invalid_api_key")
    if isinstance(exc, groq.RateLimitError):
        return LLMError("Groq rate limit reached. Wait a moment and retry.", 429, "rate_limited")
    if isinstance(exc, groq.NotFoundError):
        return LLMError(f"Model '{model}' is not available on Groq. Change GROQ_MODEL in backend/.env.", 404, "model_unavailable")
    if isinstance(exc, groq.APITimeoutError):
        return LLMError("The request to Groq timed out. Please retry.", 504, "timeout")
    if isinstance(exc, groq.APIConnectionError):
        return LLMError("Could not reach Groq. Check your internet connection.", 503, "network_error")
    if isinstance(exc, groq.BadRequestError):
        return LLMError(f"Groq rejected the request: {getattr(exc, 'message', str(exc))}", 400, "bad_request")
    if isinstance(exc, groq.APIStatusError):
        return LLMError(f"Groq API error (HTTP {exc.status_code}). Please retry.", 502, "api_error")
    log.exception("Unexpected LLM error", exc_info=exc)
    return LLMError("Unexpected error while contacting the language model.", 500, "unknown")


class GroqClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: groq.AsyncGroq | None = None
        self._models_cache: tuple[float, list[str]] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.groq_api_key and self.settings.groq_model)

    def _get(self) -> groq.AsyncGroq:
        if not self.settings.groq_api_key:
            raise LLMError("GROQ_API_KEY is not set. Add it to backend/.env and restart the backend.", 503, "not_configured")
        if not self.settings.groq_model:
            raise LLMError("GROQ_MODEL is not set. Add it to backend/.env and restart the backend.", 503, "not_configured")
        if self._client is None:
            self._client = groq.AsyncGroq(api_key=self.settings.groq_api_key, timeout=self.settings.groq_timeout_seconds, max_retries=1)
        return self._client

    async def list_models(self) -> list[str]:
        """Model IDs available to this key (cached for 5 minutes)."""
        if self._models_cache and time.time() - self._models_cache[0] < 300:
            return self._models_cache[1]
        try:
            resp = await self._get().models.list()
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _map_error(exc, self.settings.groq_model) from exc
        ids = sorted(m.id for m in resp.data)
        self._models_cache = (time.time(), ids)
        return ids

    async def complete(self, messages: list[dict], max_tokens: int) -> str:
        try:
            resp = await self._get().chat.completions.create(
                model=self.settings.groq_model, messages=messages, max_tokens=max_tokens, temperature=0.3)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _map_error(exc, self.settings.groq_model) from exc
        return resp.choices[0].message.content or ""

    async def stream(self, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        try:
            stream = await self._get().chat.completions.create(
                model=self.settings.groq_model, messages=messages, max_tokens=max_tokens, temperature=0.6, stream=True)
            async for chunk in stream:
                if chunk.choices and (delta := chunk.choices[0].delta.content):
                    yield delta
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _map_error(exc, self.settings.groq_model) from exc
