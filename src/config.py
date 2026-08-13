"""Safe configuration loading for the Phase 1 chatbot."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


class ConfigurationError(Exception):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Configuration values needed by the application."""

    api_key: str
    model: str


def load_settings() -> Settings:
    """Load settings from environment variables and validate required values."""

    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()

    if not api_key:
        raise ConfigurationError(
            "GEMINI_API_KEY is not configured. Copy .env.example to .env and add "
            "your API key locally."
        )

    if not model:
        model = DEFAULT_GEMINI_MODEL

    return Settings(api_key=api_key, model=model)
