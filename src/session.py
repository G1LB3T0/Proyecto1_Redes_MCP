"""In-memory conversation history for a single chatbot session."""

from __future__ import annotations

from typing import Any


class ConversationSession:
    """Build the explicit history required by stateless Gemini interactions."""

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []

    def add_user_message(self, message: str) -> None:
        """Append one user message in the Interactions API input format."""

        self.history.append(
            {
                "type": "user_input",
                "content": [{"type": "text", "text": message}],
            }
        )

    def add_model_steps(self, steps: tuple[dict[str, Any], ...]) -> None:
        """Append every generated step so the next turn preserves context."""

        self.history.extend(steps)

    def discard_last_user_message(self) -> None:
        """Remove an unsent user turn when its API request failed."""

        if self.history and self.history[-1].get("type") == "user_input":
            self.history.pop()

    def restore(self, history_length: int) -> None:
        """Restore a prior local checkpoint after an incomplete turn."""

        if history_length < 0 or history_length > len(self.history):
            raise ValueError("Invalid conversation history checkpoint.")
        del self.history[history_length:]
