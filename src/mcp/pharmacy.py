"""Client configuration for the local manual pharmacy inventory MCP server."""

from __future__ import annotations

import sys

from src.config import PharmacySettings
from src.mcp.http_client import HttpMcpClient
from src.mcp.stdio_client import StdioMcpClient


def create_pharmacy_client(
    timeout_seconds: float = 20.0, *, settings: PharmacySettings | None = None,
) -> StdioMcpClient | HttpMcpClient:
    """Use identical inventory tools through either manually implemented transport."""

    if settings is not None and settings.transport == "http":
        return HttpMcpClient(url=settings.url, auth_token=settings.token,
                             timeout_seconds=timeout_seconds, tls_keylog_file=settings.tls_keylog_file)
    return StdioMcpClient(
        server_name="pharmacy",
        command=(sys.executable, "-m", "src.custom_mcp.stdio_server"),
        timeout_seconds=timeout_seconds,
    )
