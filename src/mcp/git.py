"""Configuration for the official Git MCP server demo."""

from __future__ import annotations

from pathlib import Path

from src.mcp.stdio_client import StdioMcpClient


GIT_SERVER_PACKAGE = "mcp-server-git"


def create_git_client(
    repository: Path, timeout_seconds: float = 20.0
) -> StdioMcpClient:
    """Create a client for the official Git MCP server and one demo repository."""

    return StdioMcpClient(
        server_name="git",
        command=(
            "uvx",
            GIT_SERVER_PACKAGE,
            "--repository",
            str(repository.resolve()),
        ),
        timeout_seconds=timeout_seconds,
    )
