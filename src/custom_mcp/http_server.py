"""Manual MCP Streamable HTTP endpoint over WSGI; JSON responses, no SSE stream.

Protocol reference: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
Run with one Gunicorn worker and multiple threads: session state is process-local.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import json
import logging
import os
import secrets
import threading
import time
from typing import Any

from src.custom_mcp.inventory_service import InventoryService
from src.custom_mcp.server_core import PharmacyMcpServer, _error_response
from src.custom_mcp.stdio_server import _reject_non_json_number
from src.mcp.protocol import MCP_PROTOCOL_VERSION


MAX_BODY_BYTES = 65_536
LOGGER = logging.getLogger(__name__)


@dataclass
class Session:
    server: PharmacyMcpServer
    last_seen: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class PharmacyHttpApp:
    """Expose the existing dispatcher with isolated, expiring HTTP sessions."""

    def __init__(
        self, auth_token: str, *, allowed_origins: tuple[str, ...] = (),
        session_ttl: float = 1800, max_sessions: int = 128,
    ) -> None:
        if not auth_token or session_ttl <= 0 or max_sessions < 1:
            raise ValueError("An access token and positive session limits are required.")
        self._auth_token = auth_token
        self._allowed_origins = set(allowed_origins)
        self._session_ttl = session_ttl
        self._max_sessions = max_sessions
        self._inventory = InventoryService()
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def __call__(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "")
        path = environ.get("PATH_INFO", "")
        if path == "/healthz" and method == "GET":
            return self._reply(start_response, "200 OK", {"status": "ok"})
        if path != "/mcp":
            return self._reply(start_response, "404 Not Found", {"error": "Unknown endpoint"})
        origin = environ.get("HTTP_ORIGIN")
        if origin is not None and origin not in self._allowed_origins:
            return self._reply(start_response, "403 Forbidden", {"error": "Origin is not allowed"})
        authorization = environ.get("HTTP_AUTHORIZATION", "")
        if not hmac.compare_digest(authorization.encode(), ("Bearer " + self._auth_token).encode()):
            return self._reply(start_response, "401 Unauthorized", {"error": "Authentication required"},
                               [("WWW-Authenticate", 'Bearer realm="pharmacy-mcp"')])
        version = environ.get("HTTP_MCP_PROTOCOL_VERSION")
        if version is not None and version != MCP_PROTOCOL_VERSION:
            return self._reply(start_response, "400 Bad Request", {"error": "Unsupported MCP protocol version"})
        if method not in {"POST", "DELETE"}:
            # An HTTP MCP server may decline the optional GET/SSE channel with 405.
            return self._reply(start_response, "405 Method Not Allowed", None, [("Allow", "POST, DELETE")])

        session_id = environ.get("HTTP_MCP_SESSION_ID")
        now = time.monotonic()
        with self._lock:
            expired = [key for key, value in self._sessions.items() if now - value.last_seen >= self._session_ttl]
            for key in expired:
                del self._sessions[key]
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_seen = now
        if session_id is not None and session is None:
            return self._reply(start_response, "404 Not Found", {"error": "MCP session has expired or does not exist"})
        if method == "DELETE":
            if session_id is None:
                return self._reply(start_response, "400 Bad Request", {"error": "MCP-Session-Id is required"})
            with self._lock:
                self._sessions.pop(session_id, None)
            return self._reply(start_response, "204 No Content", None)

        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            return self._reply(start_response, "415 Unsupported Media Type", {"error": "Use application/json"})
        accept = {part.split(";", 1)[0].strip().lower() for part in environ.get("HTTP_ACCEPT", "").split(",")}
        if not {"application/json", "text/event-stream"}.issubset(accept):
            return self._reply(start_response, "406 Not Acceptable", {"error": "Accept JSON and event-stream responses"})
        try:
            length = int(environ.get("CONTENT_LENGTH", ""))
        except (ValueError, TypeError):
            return self._reply(start_response, "411 Length Required", {"error": "Content-Length is required"})
        if length < 1 or length > MAX_BODY_BYTES:
            return self._reply(start_response, "413 Content Too Large", {"error": "Invalid message size"})
        try:
            raw = environ["wsgi.input"].read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            message = json.loads(raw.decode("utf-8"), parse_constant=_reject_non_json_number)
        except (ValueError, UnicodeError):
            return self._reply(start_response, "400 Bad Request", _error_response(None, -32700, "Parse error"))
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._reply(start_response, "400 Bad Request", _error_response(None, -32600, "Invalid Request"))
        initializing = message.get("method") == "initialize" and "id" in message
        if session is None and not initializing:
            return self._reply(start_response, "400 Bad Request", {"error": "Initialize a session first"})
        new_session = session is None
        if new_session:
            session = Session(PharmacyMcpServer(self._inventory), now)
        try:
            with session.lock:
                response = session.server.handle(message)
        except Exception:
            LOGGER.exception("Pharmacy request failed")
            request_id = message.get("id")
            if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
                request_id = None
            response = _error_response(request_id, -32603, "Internal error")
        headers: list[tuple[str, str]] = []
        if new_session and response is not None and "result" in response:
            with self._lock:
                if len(self._sessions) >= self._max_sessions:
                    return self._reply(start_response, "503 Service Unavailable", {"error": "Session limit reached"},
                                       [("Retry-After", "30")])
                session_id = secrets.token_urlsafe(32)
                self._sessions[session_id] = session
            headers.append(("MCP-Session-Id", session_id))
        if response is None:
            return self._reply(start_response, "202 Accepted", None)
        return self._reply(start_response, "200 OK", response, headers)

    @staticmethod
    def _reply(start_response: Any, status: str, value: Any, extra_headers: list | None = None) -> list[bytes]:
        body = b"" if value is None else json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        headers = [("Content-Length", str(len(body))), ("Cache-Control", "no-store")]
        if value is not None:
            headers.append(("Content-Type", "application/json; charset=utf-8"))
        start_response(status, headers + (extra_headers or []))
        return [body]


def create_app() -> PharmacyHttpApp:
    """Build the HTTP application from server-only environment configuration."""

    origins = tuple(value.strip() for value in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",") if value.strip())
    return PharmacyHttpApp(os.getenv("MCP_AUTH_TOKEN", ""), allowed_origins=origins)


if __name__ == "__main__":
    # Local development only. The deployment uses Gunicorn behind Nginx.
    from wsgiref.simple_server import make_server
    with make_server("127.0.0.1", int(os.getenv("PORT", "8091")), create_app()) as httpd:
        httpd.serve_forever()
