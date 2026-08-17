"""Sanitized wire logging for manual MCP traffic."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


LOG_DIRECTORY = Path(__file__).resolve().parent.parent.parent / "logs"
MCP_LOG_FILE = LOG_DIRECTORY / "mcp.log"
_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "authorization", "password", "secret", "token")


class McpWireLogger:
    """Write MCP requests and responses to a dedicated, sanitized log file."""

    def __init__(self, log_file: Path = MCP_LOG_FILE) -> None:
        self._logger = logging.getLogger("chatbot.mcp.wire")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        resolved_log_file = log_file.resolve()
        if not any(
            isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == resolved_log_file
            for handler in self._logger.handlers
        ):
            log_file.parent.mkdir(exist_ok=True)
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            self._logger.addHandler(handler)

    def record(
        self,
        *,
        direction: str,
        server: str,
        transport: str,
        request_id: int | str | None,
        method: str | None,
        message: Any,
    ) -> None:
        """Record one MCP wire message while redacting common credential fields."""

        serialized_message = json.dumps(
            sanitize_for_log(message), ensure_ascii=False, separators=(",", ":")
        )
        self._logger.info(
            "direction=%s server=%s transport=%s request_id=%s method=%s json=%s",
            direction,
            server,
            transport,
            request_id if request_id is not None else "-",
            method or "-",
            serialized_message,
        )


def sanitize_for_log(value: Any) -> Any:
    """Recursively redact likely credential values before a log write."""

    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if _is_sensitive_key(str(key))
            else sanitize_for_log(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_for_log(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_log(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return f"<{type(value).__name__}>"


def read_recent_entries(limit: int = 20, log_file: Path = MCP_LOG_FILE) -> list[str]:
    """Return the most recent MCP log lines without creating a log file."""

    if limit < 1:
        raise ValueError("The log entry limit must be at least 1.")
    if not log_file.is_file():
        return []
    with log_file.open("r", encoding="utf-8") as file:
        return file.read().splitlines()[-limit:]


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.lower().replace("-", "_")
    return any(part in normalized_key for part in _SENSITIVE_KEY_PARTS)
