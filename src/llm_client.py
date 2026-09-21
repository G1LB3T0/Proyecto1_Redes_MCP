"""Gemini Developer API client with stateless conversation exchanges."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, TypeAlias

from google import genai
from google.genai import types

from src.config import Settings


GeminiInput: TypeAlias = str | list[dict[str, Any]]
GeminiTools: TypeAlias = list[dict[str, Any]]
LOGGER = logging.getLogger("chatbot.llm")
GEMINI_TIMEOUT_SECONDS = 60


class GeminiRequestError(Exception):
    """Raised when a Gemini request cannot produce a usable response."""


@dataclass(frozen=True)
class GeminiResponse:
    """Safe data returned from a completed Gemini interaction."""

    text: str
    interaction_id: str | None
    steps: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class GeminiInteraction:
    """Raw interaction data, including function-call steps when present."""

    text: str | None
    interaction_id: str | None
    steps: tuple[dict[str, Any], ...]


class GeminiClient:
    """Small wrapper around the official Google GenAI SDK."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.model
        self._client = genai.Client(
            api_key=settings.api_key,
            http_options=types.HttpOptions(
                timeout=GEMINI_TIMEOUT_SECONDS * 1000,
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

        interaction = self.interact(interaction_input)
        if interaction.text is None:
            raise GeminiRequestError(
                "Gemini returned a response without usable text. Try a different "
                "prompt or review the API response."
            )
        return GeminiResponse(
            text=interaction.text,
            interaction_id=interaction.interaction_id,
            steps=interaction.steps,
        )

    def interact(
        self,
        interaction_input: GeminiInput,
        tools: GeminiTools | None = None,
        system_instruction: str | None = None,
    ) -> GeminiInteraction:
        """Create a stateless interaction, optionally with normal function tools."""

        try:
            request: dict[str, Any] = {
                "model": self._model,
                "input": interaction_input,
                "store": False,
            }
            if tools:
                request["tools"] = tools
            if system_instruction:
                request["system_instruction"] = system_instruction
            interaction = self._client.interactions.create(**request)
        except Exception as error:
            LOGGER.warning(
                "Gemini request failed: error_type=%s status_code=%s",
                type(error).__name__,
                _get_status_code(error),
            )
            raise GeminiRequestError(_friendly_error_message(error)) from error

        interaction_id = getattr(interaction, "id", None)
        LOGGER.info(
            "Gemini response received: model=%s interaction_id=%s",
            self._model,
            interaction_id or "not_exposed",
        )
        response_text = getattr(interaction, "output_text", None)
        return GeminiInteraction(
            text=response_text.strip()
            if isinstance(response_text, str) and response_text.strip()
            else None,
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
        return f"Gemini did not respond within {GEMINI_TIMEOUT_SECONDS} seconds. Please try again."
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
