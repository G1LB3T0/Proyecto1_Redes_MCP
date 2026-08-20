"""Manual MCP request dispatcher for the local pharmacy inventory server."""

from __future__ import annotations

import json
from typing import Any

from src.custom_mcp.inventory_service import InventoryService
from src.mcp.protocol import (
    INITIALIZE_METHOD,
    INITIALIZED_NOTIFICATION,
    JSON_RPC_VERSION,
    MCP_PROTOCOL_VERSION,
    TOOLS_CALL_METHOD,
    TOOLS_LIST_METHOD,
)


class PharmacyMcpServer:
    """Handle the small MCP surface required by the local pharmacy server."""

    def __init__(self, inventory: InventoryService | None = None) -> None:
        self._inventory = inventory or InventoryService()
        self._client_initialized = False

    def handle(self, message: Any) -> dict[str, Any] | None:
        """Process one decoded JSON-RPC message and return its response if needed."""

        if not isinstance(message, dict):
            return _error_response(None, -32600, "Invalid Request")
        request_id = message.get("id")
        if message.get("jsonrpc") != JSON_RPC_VERSION:
            return _error_response(request_id, -32600, "Invalid Request")
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return _error_response(request_id, -32600, "Invalid Request")
        if "id" not in message:
            self._handle_notification(method, message.get("params"))
            return None
        if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
            return _error_response(None, -32600, "Invalid Request")

        try:
            result = self._handle_request(method, message.get("params"))
        except _InvalidParams as error:
            return _error_response(request_id, -32602, str(error))
        except _MethodNotFound:
            return _error_response(request_id, -32601, "Method not found")
        except _NotInitialized:
            return _error_response(request_id, -32002, "Server not initialized")
        return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}

    def _handle_notification(self, method: str, _params: Any) -> None:
        if method == INITIALIZED_NOTIFICATION:
            self._client_initialized = True

    def _handle_request(self, method: str, params: Any) -> Any:
        if method == INITIALIZE_METHOD:
            return self._initialize(params)
        if not self._client_initialized:
            raise _NotInitialized()
        if method == TOOLS_LIST_METHOD:
            _require_object_or_missing(params)
            return {"tools": self._inventory.tools()}
        if method == TOOLS_CALL_METHOD:
            return self._call_tool(params)
        raise _MethodNotFound()

    def _initialize(self, params: Any) -> dict[str, Any]:
        parameters = _require_object(params)
        protocol_version = parameters.get("protocolVersion")
        client_info = parameters.get("clientInfo")
        if protocol_version != MCP_PROTOCOL_VERSION or not isinstance(client_info, dict):
            raise _InvalidParams("Unsupported initialize parameters")
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "pharmacy-inventory", "version": "0.1.0"},
        }

    def _call_tool(self, params: Any) -> dict[str, Any]:
        parameters = _require_object(params)
        name = parameters.get("name")
        arguments = parameters.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise _InvalidParams("tools/call requires a name and an arguments object")
        try:
            result = self._inventory.call_tool(name, arguments)
        except (LookupError, ValueError) as error:
            return _tool_result({"error": str(error)}, is_error=True)
        return _tool_result(result, is_error=False)


class _InvalidParams(Exception):
    pass


class _MethodNotFound(Exception):
    pass


class _NotInitialized(Exception):
    pass


def _require_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _InvalidParams("params must be an object")
    return value


def _require_object_or_missing(value: Any) -> None:
    if value is not None and not isinstance(value, dict):
        raise _InvalidParams("params must be an object")


def _tool_result(value: Any, *, is_error: bool) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
        "structuredContent": value,
        "isError": is_error,
    }


def _error_response(request_id: int | str | None, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSON_RPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }
