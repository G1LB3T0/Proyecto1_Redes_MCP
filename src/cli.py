"""Interactive command-line chatbot entry point."""

from __future__ import annotations

import logging

from src.app_logging import configure_logging
from src.config import ConfigurationError, load_settings
from src.llm_client import GeminiClient, GeminiRequestError
from src.session import ConversationSession


def main() -> int:
    """Start an interactive chat without preserving conversation history."""

    configure_logging()
    logger = logging.getLogger("chatbot.cli")

    try:
        settings = load_settings()
    except ConfigurationError as error:
        logger.error("Configuration error: error_type=%s", type(error).__name__)
        print(f"Configuration error: {error}")
        return 1

    logger.info("Chatbot session started: model=%s", settings.model)
    client = GeminiClient(settings)
    try:
        return run_chat(client, settings.model, ConversationSession())
    finally:
        client.close()
        logger.info("Chatbot session ended")


def run_chat(client: GeminiClient, model: str, session: ConversationSession) -> int:
    """Read prompts and display Gemini responses with session-only context."""

    logger = logging.getLogger("chatbot.cli")
    print("Chatbot CC3067")
    print(f"Model: {model}")
    print("Type 'exit' to quit.")

    try:
        while True:
            user_message = input("\nYou: ").strip()

            if user_message.lower() == "exit":
                logger.info("Session closed by exit command")
                print("Session closed.")
                return 0
            if not user_message:
                continue

            session.add_user_message(user_message)
            print("Assistant: waiting for Gemini...")
            try:
                response = client.ask(session.history)
            except GeminiRequestError as error:
                session.discard_last_user_message()
                logger.warning("Gemini request did not complete; user turn discarded")
                print(f"Gemini error: {error}")
                continue

            session.add_model_steps(response.steps)
            print(f"Assistant: {response.text}")
    except KeyboardInterrupt:
        logger.info("Session closed by Ctrl+C")
        print("\nSession closed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
