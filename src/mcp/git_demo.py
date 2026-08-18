"""Manual, Gemini-free validation of Filesystem and Git MCP servers."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.mcp.filesystem import DEMO_WORKSPACE, create_filesystem_client
from src.mcp.git import create_git_client


GIT_DEMO_REPOSITORY = DEMO_WORKSPACE / "git_demo"
README_PATH = GIT_DEMO_REPOSITORY / "README.md"
COMMIT_MESSAGE = "docs: add MCP demo readme"
REQUIRED_GIT_TOOLS = {"git_status", "git_add", "git_commit", "git_log"}


def main() -> int:
    """Exercise official MCP servers without involving Gemini."""

    prepare_demo_repository()

    with create_git_client(GIT_DEMO_REPOSITORY) as git_client:
        git_tools = git_client.list_tools()
        git_tool_names = tool_names(git_tools)
        print("Git MCP tools:")
        print("\n".join(git_tool_names))
        missing_tools = REQUIRED_GIT_TOOLS.difference(git_tool_names)
        if missing_tools:
            raise RuntimeError(
                "Git MCP did not advertise required tools: "
                + ", ".join(sorted(missing_tools))
            )

        status_before = git_client.call_tool("git_status")
        with create_filesystem_client() as filesystem_client:
            filesystem_client.connect()
            filesystem_client.call_tool(
                "write_file",
                {"path": str(README_PATH), "content": demo_readme_content()},
            )
        add_result = git_client.call_tool("git_add", {"files": ["README.md"]})
        commit_result = git_client.call_tool("git_commit", {"message": COMMIT_MESSAGE})
        log_result = git_client.call_tool("git_log", {"max_count": 1})

    print_result("git_status before Filesystem MCP write", status_before)
    print_result("git_add", add_result)
    print_result("git_commit", commit_result)
    print_result("git_log", log_result)
    print(f"Demo repository: {GIT_DEMO_REPOSITORY}")
    return 0


def prepare_demo_repository() -> None:
    """Initialize and identify only the disposable Git demonstration repository."""

    resolved_workspace = DEMO_WORKSPACE.resolve()
    resolved_repository = GIT_DEMO_REPOSITORY.resolve()
    if not resolved_repository.is_relative_to(resolved_workspace):
        raise RuntimeError("Git demo repository must stay inside demo_workspace.")

    resolved_repository.mkdir(parents=True, exist_ok=True)
    run_git("init")
    run_git("config", "user.name", "CC3067 Demo")
    run_git("config", "user.email", "cc3067-demo@example.local")


def run_git(*arguments: str) -> None:
    """Run normal Git only within the disposable demo repository."""

    try:
        subprocess.run(
            ("git", *arguments),
            cwd=GIT_DEMO_REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "Unknown Git error."
        raise RuntimeError(f"Could not prepare the Git demo repository: {detail}") from error


def demo_readme_content() -> str:
    """Return a changing demo value so repeated manual runs create a commit."""

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"CC3067 MCP Git demo\nRun: {timestamp}\n"


def tool_names(tools: list[dict[str, Any]]) -> list[str]:
    """Extract valid tool names from a real MCP tools/list result."""

    return sorted(tool["name"] for tool in tools if isinstance(tool.get("name"), str))


def print_result(label: str, result: Any) -> None:
    """Print an MCP result without changing it."""

    print(f"{label} result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
