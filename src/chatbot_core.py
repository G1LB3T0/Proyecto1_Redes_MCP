"""Interface-independent chatbot orchestration for CLI and a future API."""

from __future__ import annotations

import logging

from src.config import Settings
from src.llm_client import GeminiClient, GeminiRequestError
from src.mcp.coordinator import McpCoordinator, McpCoordinatorError, McpServerBinding, git_demo_argument_preparer
from src.mcp.filesystem import create_filesystem_client
from src.mcp.git import create_git_client
from src.mcp.git_demo import GIT_DEMO_REPOSITORY, prepare_demo_repository
from src.mcp.pharmacy import create_pharmacy_client
from src.session import ConversationSession


class ChatbotCoreError(Exception):
    """Raised when a user turn cannot be completed safely."""


class ChatbotCore:
    """Own the session, Gemini client, and manual MCP coordinator."""

    def __init__(self, client: GeminiClient, coordinator: McpCoordinator) -> None:
        self._client = client
        self._coordinator = coordinator
        self._session = ConversationSession()
        self._logger = logging.getLogger("chatbot.core")

    def send_message(self, message: str) -> str:
        """Process one message without coupling the logic to a user interface."""

        if not isinstance(message, str) or not message.strip():
            raise ValueError("A chat message must not be empty.")
        checkpoint = len(self._session.history)
        self._session.add_user_message(message.strip())
        try:
            response = self._coordinator.complete(self._client, self._session.history)
        except (GeminiRequestError, McpCoordinatorError) as error:
            self._session.restore(checkpoint)
            self._logger.warning("Chatbot turn failed: error_type=%s", type(error).__name__)
            raise ChatbotCoreError(str(error)) from error
        self._session.add_model_steps(response.steps)
        return response.text

    def close(self) -> None:
        """Release MCP subprocesses and Gemini network resources."""

        self._coordinator.close()
        self._client.close()


def create_demo_chatbot(settings: Settings) -> ChatbotCore:
    """Build the chatbot with local developer tools and local or remote pharmacy."""

    if not (GIT_DEMO_REPOSITORY / ".git").is_dir():
        prepare_demo_repository()
    git_client = create_git_client(GIT_DEMO_REPOSITORY)
    coordinator = McpCoordinator(
        (
            McpServerBinding("filesystem", create_filesystem_client()),
            McpServerBinding("pharmacy", create_pharmacy_client(settings=settings.pharmacy)),
            McpServerBinding(
                "git",
                git_client,
                prepare_arguments=git_demo_argument_preparer(GIT_DEMO_REPOSITORY),
            ),
        ),
        system_instruction=(
            "Use the provided MCP function tools only when the user requests an "
            "operation they support. Filesystem MCP is restricted to "
            f"{GIT_DEMO_REPOSITORY.parent.resolve()}. Git MCP is restricted to "
            f"{GIT_DEMO_REPOSITORY.resolve()}. Do not attempt to use paths outside "
            "those locations. Pharmacy MCP provides demo inventory data only; do not "
            "give medical advice or make claims about medication use."
        ),
    )
    return ChatbotCore(GeminiClient(settings), coordinator)
