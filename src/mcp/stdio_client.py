"""Manual stdio transport for communicating with MCP servers over JSON-RPC."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.mcp.logging import McpWireLogger
from src.mcp.protocol import (
    INITIALIZE_METHOD,
    INITIALIZED_NOTIFICATION,
    MCP_PROTOCOL_VERSION,
    TOOLS_CALL_METHOD,
    TOOLS_LIST_METHOD,
    JsonRpcProtocolError,
    RequestIdGenerator,
    build_notification,
    build_request,
    is_response,
    validate_response,
)


class McpTransportError(Exception):
    """Raised when the stdio transport cannot complete an MCP exchange."""


@dataclass(frozen=True)
class McpServerInfo:
    """Negotiated server information returned from initialize."""

    protocol_version: str
    capabilities: dict[str, Any]
    server_info: dict[str, Any]


class StdioMcpClient:
    """A manually implemented MCP client for one stdio server process."""

    def __init__(
        self,
        *,
        server_name: str,
        command: Sequence[str],
        timeout_seconds: float = 10.0,
        wire_logger: McpWireLogger | None = None,
    ) -> None:
        if not server_name.strip():
            raise ValueError("server_name must not be empty.")
        if not command:
            raise ValueError("command must contain a program and its arguments.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._server_name = server_name
        self._command = tuple(command)
        self._timeout_seconds = timeout_seconds
        self._wire_logger = wire_logger or McpWireLogger()
        self._process: subprocess.Popen[str] | None = None
        self._request_ids = RequestIdGenerator()
        self._responses: queue.Queue[dict[str, Any] | Exception] = queue.Queue()
        self._deferred_responses: dict[int | str, dict[str, Any]] = {}
        self._request_methods: dict[int | str, str] = {}
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._initialized = False
        self._server_info: McpServerInfo | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: queue.Queue[str] = queue.Queue(maxsize=25)

    def __enter__(self) -> "StdioMcpClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def server_info(self) -> McpServerInfo:
        """Return the information negotiated during the MCP handshake."""

        if self._server_info is None:
            raise McpTransportError("MCP server has not completed initialization.")
        return self._server_info

    def connect(self) -> McpServerInfo:
        """Start the subprocess and complete the mandatory MCP lifecycle handshake."""

        if self._initialized:
            return self.server_info
        self._start_process()
        try:
            result = self._request(
                INITIALIZE_METHOD,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "cc3067-manual-mcp-client", "version": "0.1.0"},
                },
            )
            if not isinstance(result, dict):
                raise JsonRpcProtocolError("MCP initialize result must be an object.")
            protocol_version = result.get("protocolVersion")
            capabilities = result.get("capabilities")
            server_info = result.get("serverInfo", {})
            if not isinstance(protocol_version, str) or not isinstance(capabilities, dict):
                raise JsonRpcProtocolError("MCP initialize result is missing protocolVersion or capabilities.")
            if not isinstance(server_info, dict):
                raise JsonRpcProtocolError("MCP initialize result contains an invalid serverInfo object.")
            self._server_info = McpServerInfo(protocol_version, capabilities, server_info)
            self._notify(INITIALIZED_NOTIFICATION)
            self._initialized = True
            return self._server_info
        except Exception:
            self.close()
            raise

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the tools currently advertised by the connected MCP server."""

        self._require_initialized()
        result = self._request(TOOLS_LIST_METHOD)
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            raise JsonRpcProtocolError("MCP tools/list result must contain a tools array.")
        tools = result["tools"]
        if not all(isinstance(tool, dict) for tool in tools):
            raise JsonRpcProtocolError("MCP tools/list returned an invalid tool definition.")
        return tools

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        """Call one advertised MCP tool and return its server result."""

        self._require_initialized()
        if not isinstance(name, str) or not name.strip():
            raise ValueError("MCP tool name must be a non-empty string.")
        if arguments is not None and not isinstance(arguments, Mapping):
            raise ValueError("MCP tool arguments must be an object.")
        return self._request(
            TOOLS_CALL_METHOD,
            {"name": name, "arguments": dict(arguments or {})},
        )

    def close(self) -> None:
        """Stop the subprocess and release its pipes without blocking indefinitely."""

        process = self._process
        self._initialized = False
        self._server_info = None
        if process is None:
            return
        self._process = None
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def _start_process(self) -> None:
        if self._process is not None:
            return
        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as error:
            raise McpTransportError(
                f"Could not start MCP server '{self._server_name}': {error}"
            ) from error

        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        request_id = self._request_ids.next()
        message = build_request(request_id, method, params)
        self._request_methods[request_id] = method
        self._send(message, request_id=request_id, method=method)

        deferred = self._deferred_responses.pop(request_id, None)
        if deferred is not None:
            return validate_response(deferred, request_id)

        deadline = time.monotonic() + self._timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpTransportError(
                    f"Timed out waiting for {method!r} from MCP server '{self._server_name}'."
                )
            try:
                incoming = self._responses.get(timeout=remaining)
            except queue.Empty as error:
                raise McpTransportError(
                    f"Timed out waiting for {method!r} from MCP server '{self._server_name}'."
                ) from error
            if isinstance(incoming, Exception):
                raise McpTransportError(
                    f"MCP server '{self._server_name}' sent invalid stdout: {incoming}"
                ) from incoming
            if not is_response(incoming):
                continue
            response_id = incoming.get("id")
            if response_id == request_id:
                return validate_response(incoming, request_id)
            if isinstance(response_id, (int, str)) and not isinstance(response_id, bool):
                self._deferred_responses[response_id] = incoming

    def _notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self._send(build_notification(method, params), request_id=None, method=method)

    def _send(self, message: dict[str, Any], *, request_id: int | str | None, method: str) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise McpTransportError("MCP server process is not running.")
        self._wire_logger.record(
            direction="CLIENT->SERVER",
            server=self._server_name,
            transport="stdio",
            request_id=request_id,
            method=method,
            message=message,
        )
        try:
            with self._write_lock:
                process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise McpTransportError(
                f"MCP server '{self._server_name}' closed its input stream."
            ) from error

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise JsonRpcProtocolError("MCP stdout message must be a JSON object.")
                request_id = message.get("id")
                if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
                    request_id = None
                method = self._request_methods.get(request_id) if request_id is not None else message.get("method")
                self._wire_logger.record(
                    direction="SERVER->CLIENT",
                    server=self._server_name,
                    transport="stdio",
                    request_id=request_id,
                    method=method if isinstance(method, str) else None,
                    message=message,
                )
                self._responses.put(message)
            except (json.JSONDecodeError, JsonRpcProtocolError) as error:
                self._responses.put(error)

    def _drain_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            try:
                self._stderr_tail.put_nowait(line.rstrip())
            except queue.Full:
                try:
                    self._stderr_tail.get_nowait()
                except queue.Empty:
                    pass
                self._stderr_tail.put_nowait(line.rstrip())

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise McpTransportError("Connect to the MCP server before using its tools.")
