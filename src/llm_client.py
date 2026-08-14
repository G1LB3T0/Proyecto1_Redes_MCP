"""Gemini Developer API client for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias

from google import genai
from google.genai import types

from src.config import Settings


GeminiInput: TypeAlias = str | list[dict[str, Any]]


class GeminiRequestError(Exception):
    """Raised when a Gemini request cannot produce a usable response."""


@dataclass(frozen=True)
class GeminiResponse:
    """Safe data returned from a completed Gemini interaction."""

    text: str
    interaction_id: str | None
    steps: tuple[dict[str, Any], ...]


class GeminiClient:
    """Small wrapper around the official Google GenAI SDK."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.model
        self._client = genai.Client(
            api_key=settings.api_key,
            http_options=types.HttpOptions(
                timeout=15_000,
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    initial_delay=0.5,
                    max_delay=1.0,
                    exp_base=2.0,
                    jitter=0.0,
                    http_status_codes=[408, 500, 502, 503, 504],
                ),
            ),
        )

    def ask(self, interaction_input: GeminiInput) -> GeminiResponse:
        """Send stateless input through the Interactions API."""

        try:
            interaction = self._client.interactions.create(
                model=self._model,
                input=interaction_input,
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
        return GeminiResponse(
            text=response_text.strip(),
            interaction_id=interaction_id,
            steps=_serialize_steps(interaction),
        )

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
    if isinstance(error, TimeoutError) or "timeout" in error_name:
        return "Gemini did not respond within 15 seconds. Please try again."
    if isinstance(error, ConnectionError) or any(
        marker in error_name for marker in ("connect", "network", "transport")
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


def _serialize_steps(interaction: Any) -> tuple[dict[str, Any], ...]:
    """Preserve every model step required in a later stateless request."""

    raw_steps = getattr(interaction, "steps", None)
    if not raw_steps:
        raise GeminiRequestError("Gemini returned no conversation steps to preserve.")

    serialized_steps: list[dict[str, Any]] = []
    for step in raw_steps:
        dump_step = getattr(step, "model_dump", None)
        if not callable(dump_step):
            raise GeminiRequestError("Gemini returned a conversation step in an unknown format.")

        serialized_step = dump_step()
        if not isinstance(serialized_step, dict):
            raise GeminiRequestError("Gemini returned a conversation step in an unknown format.")
        serialized_steps.append(serialized_step)

    return tuple(serialized_steps)
