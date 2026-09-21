"""Interactive command-line chatbot entry point."""

from __future__ import annotations

import logging

from src.app_logging import configure_logging
from src.chatbot_core import ChatbotCore, ChatbotCoreError, create_demo_chatbot
from src.config import ConfigurationError, load_settings
from src.mcp.logging import read_recent_entries


def main() -> int:
    """Start an interactive chat with session-only conversation history."""

    configure_logging()
    logger = logging.getLogger("chatbot.cli")

    try:
        settings = load_settings()
        chatbot = create_demo_chatbot(settings)
    except (ConfigurationError, ValueError, RuntimeError, OSError) as error:
        logger.error("Configuration error: error_type=%s", type(error).__name__)
        print(f"Configuration error: {error}")
        return 1

    logger.info("Chatbot session started: model=%s", settings.model)
    print(f"Pharmacy MCP transport: {settings.pharmacy.transport}")
    try:
        return run_chat(chatbot, settings.model)
    finally:
        chatbot.close()
        logger.info("Chatbot session ended")


def run_chat(chatbot: ChatbotCore, model: str) -> int:
    """Read prompts and display answers from the interface-independent core."""

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
            if user_message.lower() == "/mcp-log":
                entries = read_recent_entries()
                if entries:
                    print("\n".join(entries))
                else:
                    print("No MCP log entries yet.")
                continue
            if not user_message:
                continue

            print("Assistant: waiting for Gemini...")
            try:
                response = chatbot.send_message(user_message)
            except ChatbotCoreError as error:
                logger.warning("Chatbot request did not complete; user turn discarded")
                print(f"Chatbot error: {error}")
                continue

            print(f"Assistant: {response}")
    except (KeyboardInterrupt, EOFError):
        logger.info("Session closed by Ctrl+C")
        print("\nSession closed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
