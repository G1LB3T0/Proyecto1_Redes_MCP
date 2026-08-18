"""Configuration for the official Filesystem MCP server demo."""

from __future__ import annotations

from pathlib import Path

from src.mcp.stdio_client import StdioMcpClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_WORKSPACE = PROJECT_ROOT / "demo_workspace"
FILESYSTEM_SERVER_PACKAGE = "@modelcontextprotocol/server-filesystem"


def create_filesystem_client(timeout_seconds: float = 20.0) -> StdioMcpClient:
    """Create a client restricted to the project's isolated demo workspace."""

    DEMO_WORKSPACE.mkdir(exist_ok=True)
    return StdioMcpClient(
        server_name="filesystem",
        command=(
            "cmd",
            "/c",
            "npx",
            "-y",
            FILESYSTEM_SERVER_PACKAGE,
            str(DEMO_WORKSPACE.resolve()),
        ),
        timeout_seconds=timeout_seconds,
    )
