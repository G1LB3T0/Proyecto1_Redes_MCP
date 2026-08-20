"""Client configuration for the local manual pharmacy inventory MCP server."""

from __future__ import annotations

import sys

from src.mcp.stdio_client import StdioMcpClient


def create_pharmacy_client(timeout_seconds: float = 10.0) -> StdioMcpClient:
    """Create a stdio client that starts this repository's local MCP server."""

    return StdioMcpClient(
        server_name="pharmacy",
        command=(sys.executable, "-m", "src.custom_mcp.stdio_server"),
        timeout_seconds=timeout_seconds,
    )
