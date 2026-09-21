"""Manual Streamable HTTP MCP client with verified TLS and optional capture keys."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import ssl
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from src.mcp.logging import McpWireLogger
from src.mcp.protocol import MCP_PROTOCOL_VERSION, JsonRpcProtocolError, RequestIdGenerator, build_notification, build_request, validate_response
from src.mcp.stdio_client import McpServerInfo, McpTransportError


MAX_RESPONSE_BYTES = 1_048_576


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _SessionExpired(McpTransportError):
    pass


class HttpMcpClient:
    """Expose the same methods as the stdio client over independent HTTP POSTs."""

    def __init__(self, *, url: str, auth_token: str, server_name: str = "pharmacy",
                 timeout_seconds: float = 20, tls_keylog_file: Path | None = None,
                 wire_logger: McpWireLogger | None = None) -> None:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment or parsed.query or not parsed.path):
            raise ValueError("MCP URL must identify one HTTP(S) endpoint without credentials, query or fragment.")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Remote MCP endpoints require HTTPS.")
        if not auth_token or any(char in auth_token for char in "\r\n") or timeout_seconds <= 0:
            raise ValueError("A valid MCP access token and positive timeout are required.")
        self._url = url
        self._auth_token = auth_token
        self._server_name = server_name
        self._timeout = timeout_seconds
        self._logger = wire_logger or McpWireLogger()
        self._ids = RequestIdGenerator()
        self._session_id: str | None = None
        self._info: McpServerInfo | None = None
        context = ssl.create_default_context()
        # This key log applies only to this MCP client, never to the Gemini client.
        if tls_keylog_file is not None:
            tls_keylog_file.parent.mkdir(parents=True, exist_ok=True)
            context.keylog_filename = str(tls_keylog_file)
        self._opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))

    def __enter__(self) -> "HttpMcpClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def server_info(self) -> McpServerInfo:
        if self._info is None:
            raise McpTransportError("MCP server has not completed initialization.")
        return self._info

    def connect(self) -> McpServerInfo:
        if self._info is not None:
            return self._info
        try:
            request_id = self._ids.next()
            response = self._exchange(build_request(request_id, "initialize", {
                "protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {},
                "clientInfo": {"name": "cc3067-manual-mcp-client", "version": "0.2.0"},
            }))
            result = validate_response(response, request_id)
            if (not isinstance(result, dict) or result.get("protocolVersion") != MCP_PROTOCOL_VERSION
                    or not isinstance(result.get("capabilities"), dict)
                    or not isinstance(result.get("serverInfo"), dict)):
                raise JsonRpcProtocolError("Invalid or unsupported MCP initialization response.")
            self._exchange(build_notification("notifications/initialized"))
            self._info = McpServerInfo(result["protocolVersion"], result["capabilities"], result["serverInfo"])
            return self._info
        except Exception:
            self.close()
            raise

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list")
        if (not isinstance(result, dict) or not isinstance(result.get("tools"), list)
                or not all(isinstance(tool, dict) for tool in result["tools"])):
            raise JsonRpcProtocolError("MCP tools/list returned invalid tool definitions.")
        return result["tools"]

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("MCP tool name must be a non-empty string.")
        if arguments is not None and not isinstance(arguments, Mapping):
            raise ValueError("MCP tool arguments must be an object.")
        return self._request("tools/call", {"name": name, "arguments": dict(arguments or {})})

    def close(self) -> None:
        if self._session_id is not None:
            try:
                request = Request(self._url, headers=self._headers(), method="DELETE")
                with self._opener.open(request, timeout=self._timeout) as response:
                    response.read(MAX_RESPONSE_BYTES)
            except (HTTPError, URLError, OSError):
                logging.getLogger(__name__).warning("MCP HTTP session could not be closed remotely.")
        self._session_id = None
        self._info = None

    def _request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if self._info is None:
            raise McpTransportError("Connect to the MCP server before using its tools.")
        for attempt in range(2):
            request_id = self._ids.next()
            try:
                return validate_response(self._exchange(build_request(request_id, method, params)), request_id)
            except _SessionExpired:
                self._session_id = None
                self._info = None
                if attempt:
                    raise
                self.connect()
        raise McpTransportError("Could not restore the MCP session.")

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
                   "Authorization": "Bearer " + self._auth_token, "MCP-Protocol-Version": MCP_PROTOCOL_VERSION}
        if self._session_id is not None:
            headers["MCP-Session-Id"] = self._session_id
        return headers

    def _exchange(self, message: dict[str, Any]) -> Any:
        method = message["method"]
        request_id = message.get("id")
        self._record("CLIENT->SERVER", message, method, request_id)
        request = Request(self._url, data=json.dumps(message, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                          headers=self._headers(), method="POST")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                if method == "initialize":
                    session_id = response.headers.get("MCP-Session-Id")
                    if session_id is not None and (not session_id or any(not 33 <= ord(char) <= 126 for char in session_id)):
                        raise JsonRpcProtocolError("Invalid MCP session ID.")
                    self._session_id = session_id
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise McpTransportError("MCP HTTP response exceeded the size limit.")
                if request_id is None:
                    if response.status != 202 or body:
                        raise JsonRpcProtocolError("MCP notifications require an empty HTTP 202 response.")
                    return None
                content_type = response.headers.get_content_type()
                if content_type == "application/json":
                    decoded = json.loads(body.decode("utf-8"))
                    self._record("SERVER->CLIENT", decoded, method, request_id)
                    return decoded
                if content_type == "text/event-stream":
                    return self._sse_response(body.decode("utf-8"), method, request_id)
                raise JsonRpcProtocolError("Unsupported MCP response content type.")
        except HTTPError as error:
            error.close()
            if error.code == 404 and self._session_id is not None:
                raise _SessionExpired("The remote MCP session expired.") from error
            if error.code in {401, 403}:
                raise McpTransportError("Remote MCP access was denied. Check PHARMACY_MCP_TOKEN and Origin.") from error
            raise McpTransportError(f"Remote MCP returned HTTP {error.code}.") from error
        except (URLError, OSError) as error:
            raise McpTransportError("Could not connect to remote MCP. Check its URL, TLS certificate and availability.") from error
        except (ValueError, UnicodeError) as error:
            raise JsonRpcProtocolError("The remote MCP response is not valid UTF-8 JSON.") from error

    def _sse_response(self, body: str, method: str, request_id: int) -> dict[str, Any]:
        """Read finite POST SSE responses; this server itself responds with JSON."""

        data: list[str] = []
        for line in body.replace("\r\n", "\n").split("\n") + [""]:
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                payload = "\n".join(data)
                data.clear()
                if not payload.strip():
                    continue
                message = json.loads(payload)
                self._record("SERVER->CLIENT", message, method, message.get("id") if isinstance(message, dict) else None)
                if isinstance(message, dict) and message.get("id") == request_id:
                    return message
        raise JsonRpcProtocolError("MCP event stream ended without the requested response.")

    def _record(self, direction: str, message: Any, method: str, request_id: int | None) -> None:
        self._logger.record(direction=direction, server=self._server_name, transport="http",
                            request_id=request_id, method=method, message=message)
