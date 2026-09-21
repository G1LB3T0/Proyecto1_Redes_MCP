"""Safe configuration loading for the chatbot and pharmacy transports."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


class ConfigurationError(Exception):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True)
class PharmacySettings:
    """Select a local process or the remote pharmacy endpoint."""

    transport: str = "stdio"
    url: str = ""
    token: str = field(default="", repr=False)
    tls_keylog_file: Path | None = None


@dataclass(frozen=True)
class Settings:
    """Configuration values needed by the application."""

    api_key: str = field(repr=False)
    model: str
    pharmacy: PharmacySettings = field(default_factory=PharmacySettings)


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

    return Settings(api_key=api_key, model=model, pharmacy=load_pharmacy_settings())


def load_pharmacy_settings() -> PharmacySettings:
    """Load MCP configuration without requiring a Gemini key for protocol demos."""

    load_dotenv()
    transport = os.getenv("PHARMACY_MCP_TRANSPORT", "stdio").strip().lower()
    if transport not in {"stdio", "http"}:
        raise ConfigurationError("PHARMACY_MCP_TRANSPORT must be stdio or http.")
    url = os.getenv("PHARMACY_MCP_URL", "").strip()
    token = os.getenv("PHARMACY_MCP_TOKEN", "").strip()
    if transport == "http" and (not url or not token):
        raise ConfigurationError("HTTP mode requires PHARMACY_MCP_URL and PHARMACY_MCP_TOKEN.")
    keylog = os.getenv("MCP_TLS_KEYLOG_FILE", "").strip()
    return PharmacySettings(transport, url, token, Path(keylog) if keylog else None)
