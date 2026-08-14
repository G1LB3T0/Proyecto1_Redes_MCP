"""Interactive command-line chatbot entry point."""

from __future__ import annotations

from src.config import ConfigurationError, load_settings
from src.llm_client import GeminiClient, GeminiRequestError
from src.session import ConversationSession


def main() -> int:
    """Start an interactive chat without preserving conversation history."""

    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(f"Configuration error: {error}")
        return 1

    client = GeminiClient(settings)
    try:
        return run_chat(client, settings.model, ConversationSession())
    finally:
        client.close()


def run_chat(client: GeminiClient, model: str, session: ConversationSession) -> int:
    """Read prompts and display Gemini responses with session-only context."""

    print("Chatbot CC3067")
    print(f"Model: {model}")
    print("Type 'exit' to quit.")

    try:
        while True:
            user_message = input("\nYou: ").strip()

            if user_message.lower() == "exit":
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
                print(f"Gemini error: {error}")
                continue

            session.add_model_steps(response.steps)
            print(f"Assistant: {response.text}")
    except KeyboardInterrupt:
        print("\nSession closed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
