"""Manual bridge between MCP tools and Gemini function calling."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.llm_client import GeminiClient, GeminiRequestError
from src.mcp.stdio_client import StdioMcpClient


MAX_TOOL_ROUNDS = 8


class McpCoordinatorError(Exception):
    """Raised when the host cannot complete a safe MCP function-calling turn."""


ArgumentPreparer = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class McpServerBinding:
    """One connected MCP server and its optional argument safety policy."""

    name: str
    client: StdioMcpClient
    prepare_arguments: ArgumentPreparer | None = None


@dataclass(frozen=True)
class McpToolBinding:
    """Maps Gemini's collision-free function name back to an MCP tool."""

    gemini_name: str
    server: McpServerBinding
    mcp_name: str


@dataclass(frozen=True)
class CoordinatedResponse:
    """The final text and all new steps created in one user turn."""

    text: str
    steps: tuple[dict[str, Any], ...]


class McpCoordinator:
    """Discover MCP tools, dispatch calls manually, and return function results."""

    def __init__(self, servers: Sequence[McpServerBinding]) -> None:
        if not servers:
            raise ValueError("At least one MCP server binding is required.")
        self._servers = tuple(servers)
        self._tool_bindings: dict[str, McpToolBinding] = {}
        self._gemini_tools: list[dict[str, Any]] = []
        self._prepared = False

    def close(self) -> None:
        """Close every local MCP subprocess owned by this coordinator."""

        for server in self._servers:
            server.client.close()
        self._prepared = False
        self._tool_bindings.clear()
        self._gemini_tools.clear()

    def complete(self, client: GeminiClient, history: list[dict[str, Any]]) -> CoordinatedResponse:
        """Run Gemini function-calling rounds until it produces final text."""

        self._prepare_tools()
        working_history = list(history)
        new_steps: list[dict[str, Any]] = []

        for _ in range(MAX_TOOL_ROUNDS):
            interaction = client.interact(working_history, self._gemini_tools)
            working_history.extend(interaction.steps)
            new_steps.extend(interaction.steps)
            calls = _function_calls(interaction.steps)
            if not calls:
                if interaction.text is None:
                    raise McpCoordinatorError("Gemini completed a turn without text or a function call.")
                return CoordinatedResponse(interaction.text, tuple(new_steps))

            result_steps = [self._execute_call(call) for call in calls]
            working_history.extend(result_steps)
            new_steps.extend(result_steps)

        raise McpCoordinatorError(
            f"Gemini exceeded the maximum of {MAX_TOOL_ROUNDS} MCP tool rounds."
        )

    def _prepare_tools(self) -> None:
        if self._prepared:
            return
        bindings: dict[str, McpToolBinding] = {}
        declarations: list[dict[str, Any]] = []
        try:
            for server in self._servers:
                server.client.connect()
                for tool in server.client.list_tools():
                    declaration, binding = _convert_tool(server, tool)
                    if binding.gemini_name in bindings:
                        raise McpCoordinatorError(
                            f"Duplicate Gemini function name: {binding.gemini_name}."
                        )
                    bindings[binding.gemini_name] = binding
                    declarations.append(declaration)
        except Exception as error:
            self.close()
            raise McpCoordinatorError(f"Could not discover MCP tools: {error}") from error

        self._tool_bindings = bindings
        self._gemini_tools = declarations
        self._prepared = True

    def _execute_call(self, call: dict[str, Any]) -> dict[str, Any]:
        call_id = call["id"]
        gemini_name = call["name"]
        arguments = call["arguments"]
        binding = self._tool_bindings.get(gemini_name)
        if binding is None:
            return _function_result(call_id, gemini_name, {"error": "Unknown MCP tool."}, True)

        try:
            prepared_arguments = dict(arguments)
            if binding.server.prepare_arguments is not None:
                prepared_arguments = binding.server.prepare_arguments(prepared_arguments)
            result = binding.server.client.call_tool(binding.mcp_name, prepared_arguments)
            is_error = isinstance(result, dict) and result.get("isError") is True
            return _function_result(call_id, gemini_name, result, is_error)
        except Exception as error:
            return _function_result(call_id, gemini_name, {"error": str(error)}, True)


def git_demo_argument_preparer(repository: Path) -> ArgumentPreparer:
    """Pin Git MCP calls to one repository, even when Gemini omits repo_path."""

    allowed_repository = repository.resolve()

    def prepare(arguments: dict[str, Any]) -> dict[str, Any]:
        requested_repository = arguments.get("repo_path")
        if requested_repository is not None:
            if not isinstance(requested_repository, str):
                raise ValueError("Git MCP repo_path must be a string.")
            if Path(requested_repository).resolve() != allowed_repository:
                raise ValueError("Git MCP is restricted to the demo repository.")
        arguments["repo_path"] = str(allowed_repository)
        return arguments

    return prepare


def _convert_tool(
    server: McpServerBinding, tool: Mapping[str, Any]
) -> tuple[dict[str, Any], McpToolBinding]:
    mcp_name = tool.get("name")
    description = tool.get("description")
    input_schema = tool.get("inputSchema")
    if not isinstance(mcp_name, str) or not mcp_name:
        raise McpCoordinatorError(f"Server '{server.name}' returned a tool without a valid name.")
    if not isinstance(input_schema, dict):
        raise McpCoordinatorError(f"Tool '{mcp_name}' returned an invalid inputSchema.")
    gemini_name = _gemini_tool_name(server.name, mcp_name)
    declaration = {
        "type": "function",
        "name": gemini_name,
        "description": description
        if isinstance(description, str) and description.strip()
        else f"MCP tool {mcp_name} from server {server.name}.",
        "parameters": input_schema,
    }
    return declaration, McpToolBinding(gemini_name, server, mcp_name)


def _gemini_tool_name(server_name: str, tool_name: str) -> str:
    normalized_server = re.sub(r"[^A-Za-z0-9_]", "_", server_name)
    normalized_tool = re.sub(r"[^A-Za-z0-9_]", "_", tool_name)
    name = f"{normalized_server}_{normalized_tool}"
    if not re.match(r"^[A-Za-z_]", name):
        name = f"mcp_{name}"
    return name[:128]


def _function_calls(steps: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for step in steps:
        if step.get("type") != "function_call":
            continue
        call_id = step.get("id")
        name = step.get("name")
        arguments = step.get("arguments")
        if not isinstance(call_id, str) or not isinstance(name, str) or not isinstance(arguments, dict):
            raise McpCoordinatorError("Gemini returned an invalid function_call step.")
        calls.append({"id": call_id, "name": name, "arguments": arguments})
    return calls


def _function_result(
    call_id: str, name: str, result: Any, is_error: bool
) -> dict[str, Any]:
    return {
        "type": "function_result",
        "call_id": call_id,
        "name": name,
        "result": json.dumps(result, ensure_ascii=False, default=str),
        "is_error": is_error,
    }
