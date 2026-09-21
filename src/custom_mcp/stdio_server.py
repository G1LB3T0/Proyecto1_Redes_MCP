"""stdio entry point for the manual local pharmacy MCP server."""

from __future__ import annotations

import json
import sys
from typing import Any

from src.custom_mcp.server_core import PharmacyMcpServer, _error_response


def main() -> int:
    """Read one JSON-RPC message per line and emit only MCP JSON on stdout."""

    _configure_utf8()
    server = PharmacyMcpServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        response = _handle_line(server, line)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


def _handle_line(server: PharmacyMcpServer, line: str) -> dict[str, Any] | None:
    try:
        message = json.loads(line, parse_constant=_reject_non_json_number)
    except (json.JSONDecodeError, ValueError):
        print("Received invalid JSON-RPC input.", file=sys.stderr)
        return _error_response(None, -32700, "Parse error")
    try:
        return server.handle(message)
    except Exception as error:
        print(f"Unhandled pharmacy MCP server error: {type(error).__name__}", file=sys.stderr)
        if isinstance(message, dict) and "id" not in message:
            return None
        request_id = message.get("id") if isinstance(message, dict) else None
        if isinstance(request_id, bool) or not isinstance(request_id, (int, str)):
            request_id = None
        return _error_response(request_id, -32603, "Internal error")


def _reject_non_json_number(value: str) -> None:
    """Python accepts NaN and Infinity by default, but JSON-RPC uses strict JSON."""

    raise ValueError(f"Invalid JSON number: {value}")


def _configure_utf8() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
