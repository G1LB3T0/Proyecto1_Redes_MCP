"""Configuration for the official Git MCP server demo."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

from src.mcp.stdio_client import StdioMcpClient


GIT_SERVER_PACKAGE = "mcp-server-git"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_uvx() -> str:
    """Find uvx even when the project's virtual environment is not on PATH."""

    executable = "uvx.exe" if os.name == "nt" else "uvx"
    scripts_directory = "Scripts" if os.name == "nt" else "bin"
    candidates = (
        Path(sys.executable).parent / executable,
        PROJECT_ROOT / ".venv" / scripts_directory / executable,
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    on_path = shutil.which("uvx")
    if on_path:
        return on_path
    raise RuntimeError(
        "Git MCP requires uvx, but it was not found beside Python, in the "
        "project's .venv, or on PATH. Install it with: python -m pip install uv"
    )


def create_git_client(
    repository: Path, timeout_seconds: float = 20.0
) -> StdioMcpClient:
    """Create a client for the official Git MCP server and one demo repository."""

    return StdioMcpClient(
        server_name="git",
        command=(
            _resolve_uvx(),
            GIT_SERVER_PACKAGE,
            "--repository",
            str(repository.resolve()),
        ),
        timeout_seconds=timeout_seconds,
    )
