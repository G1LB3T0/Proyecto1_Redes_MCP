"""Gemini Developer API client for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google import genai

from src.config import Settings


class GeminiRequestError(Exception):
    """Raised when a Gemini request cannot produce a usable response."""


@dataclass(frozen=True)
class GeminiResponse:
    """Safe data returned from a completed Gemini interaction."""

    text: str
    interaction_id: str | None


class GeminiClient:
    """Small wrapper around the official Google GenAI SDK."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.model
        self._client = genai.Client(api_key=settings.api_key)

    def ask(self, prompt: str) -> GeminiResponse:
        """Send one stateless text prompt through the Interactions API."""

        try:
            interaction = self._client.interactions.create(
                model=self._model,
                input=prompt,
                store=False,
            )
        except Exception as error:
            raise GeminiRequestError(_friendly_error_message(error)) from error

        response_text = getattr(interaction, "output_text", None)
        if not isinstance(response_text, str) or not response_text.strip():
            raise GeminiRequestError(
                "Gemini returned a response without usable text. Try a different "
                "prompt or review the API response."
            )

        interaction_id = getattr(interaction, "id", None)
        return GeminiResponse(text=response_text.strip(), interaction_id=interaction_id)

    def close(self) -> None:
        """Release the SDK's underlying network resources."""

        self._client.close()


def _friendly_error_message(error: Exception) -> str:
    """Translate common HTTP outcomes without exposing sensitive details."""

    status_code = _get_status_code(error)
    error_name = type(error).__name__.lower()

    if status_code in {401, 403}:
        return "Authentication failed. Verify GEMINI_API_KEY in your local .env file."
    if status_code == 429:
        return "Gemini quota or rate limit was reached. Wait and try again later."
    if status_code is not None and 500 <= status_code < 600:
        return "Gemini is temporarily unavailable. Wait and try again later."
    if isinstance(error, (ConnectionError, TimeoutError)) or any(
        marker in error_name
        for marker in ("connect", "network", "timeout", "transport")
    ):
        return "Network connection failed. Verify your internet connection and try again."

    return "The Gemini request failed unexpectedly. Check your configuration and try again."


def _get_status_code(error: Exception) -> int | None:
    """Read an HTTP status code when the SDK safely exposes one."""

    for attribute in ("code", "status_code"):
        value: Any = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    return None
