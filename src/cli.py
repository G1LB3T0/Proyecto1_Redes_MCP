"""Single-request command-line entry point for Gemini verification."""

from __future__ import annotations

import argparse

from src.config import ConfigurationError, load_settings
from src.llm_client import GeminiClient, GeminiRequestError


def main() -> int:
    """Send one prompt to Gemini without starting an interactive chat."""

    parser = argparse.ArgumentParser(
        description="Send one text prompt to the Gemini Developer API."
    )
    parser.add_argument("prompt", help="Text to send to Gemini.")
    arguments = parser.parse_args()

    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(f"Configuration error: {error}")
        return 1

    client = GeminiClient(settings)
    try:
        response = client.ask(arguments.prompt)
    except GeminiRequestError as error:
        print(f"Gemini error: {error}")
        return 1
    except KeyboardInterrupt:
        print("Gemini request cancelled.")
        return 130
    finally:
        client.close()

    print(f"Model: {settings.model}")
    print(f"Assistant: {response.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
