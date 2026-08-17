"""Small, transport-independent helpers for MCP JSON-RPC messages."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Mapping, TypeAlias


JSON_RPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-11-25"
INITIALIZE_METHOD = "initialize"
INITIALIZED_NOTIFICATION = "notifications/initialized"
TOOLS_LIST_METHOD = "tools/list"
TOOLS_CALL_METHOD = "tools/call"

JsonObject: TypeAlias = dict[str, Any]
RequestId: TypeAlias = int | str


class JsonRpcProtocolError(Exception):
    """Raised when a JSON-RPC message is malformed for this client."""


@dataclass(frozen=True)
class JsonRpcResponseError(Exception):
    """A JSON-RPC error returned by an MCP server."""

    code: int
    message: str
    data: Any | None = None

    def __str__(self) -> str:
        return f"MCP JSON-RPC error {self.code}: {self.message}"


class RequestIdGenerator:
    """Generate monotonically increasing request IDs for one connection."""

    def __init__(self) -> None:
        self._next_id = 1
        self._lock = Lock()

    def next(self) -> int:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
        return request_id


def build_request(
    request_id: RequestId, method: str, params: Mapping[str, Any] | None = None
) -> JsonObject:
    """Build one JSON-RPC request without selecting a transport."""

    _validate_request_id(request_id)
    _validate_method(method)
    message: JsonObject = {
        "jsonrpc": JSON_RPC_VERSION,
        "id": request_id,
        "method": method,
    }
    if params is not None:
        message["params"] = _copy_params(params)
    return message


def build_notification(
    method: str, params: Mapping[str, Any] | None = None
) -> JsonObject:
    """Build one JSON-RPC notification, which deliberately has no ID."""

    _validate_method(method)
    message: JsonObject = {"jsonrpc": JSON_RPC_VERSION, "method": method}
    if params is not None:
        message["params"] = _copy_params(params)
    return message


def validate_response(message: Any, expected_id: RequestId) -> Any:
    """Validate a response and return its result or raise its JSON-RPC error."""

    _validate_request_id(expected_id)
    if not isinstance(message, dict):
        raise JsonRpcProtocolError("MCP response must be a JSON object.")
    if message.get("jsonrpc") != JSON_RPC_VERSION:
        raise JsonRpcProtocolError("MCP response has an unsupported JSON-RPC version.")
    if message.get("id") != expected_id:
        raise JsonRpcProtocolError(
            f"MCP response ID {message.get('id')!r} does not match request {expected_id!r}."
        )

    has_result = "result" in message
    has_error = "error" in message
    if has_result == has_error:
        raise JsonRpcProtocolError("MCP response must contain exactly one of result or error.")
    if has_error:
        _raise_response_error(message["error"])
    return message["result"]


def is_response(message: Any) -> bool:
    """Return whether a decoded JSON value has the shape of a response."""

    return isinstance(message, dict) and "id" in message and (
        "result" in message or "error" in message
    )


def _raise_response_error(error: Any) -> None:
    if not isinstance(error, dict):
        raise JsonRpcProtocolError("MCP error response contains an invalid error object.")
    code = error.get("code")
    message = error.get("message")
    if isinstance(code, bool) or not isinstance(code, int) or not isinstance(message, str):
        raise JsonRpcProtocolError("MCP error response contains invalid code or message.")
    raise JsonRpcResponseError(code=code, message=message, data=error.get("data"))


def _validate_request_id(request_id: Any) -> None:
    if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
        raise JsonRpcProtocolError("JSON-RPC request IDs must be strings or integers.")


def _validate_method(method: Any) -> None:
    if not isinstance(method, str) or not method.strip():
        raise JsonRpcProtocolError("JSON-RPC methods must be non-empty strings.")


def _copy_params(params: Mapping[str, Any]) -> JsonObject:
    if not isinstance(params, Mapping):
        raise JsonRpcProtocolError("JSON-RPC params must be an object when provided.")
    return dict(params)
