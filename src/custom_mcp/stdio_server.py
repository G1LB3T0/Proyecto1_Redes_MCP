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
        return server.handle(json.loads(line))
    except json.JSONDecodeError:
        print("Received invalid JSON-RPC input.", file=sys.stderr)
        return _error_response(None, -32700, "Parse error")
    except Exception as error:
        print(f"Unhandled pharmacy MCP server error: {type(error).__name__}", file=sys.stderr)
        return _error_response(None, -32603, "Internal error")


def _configure_utf8() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
