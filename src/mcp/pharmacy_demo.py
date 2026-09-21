"""Gemini-free validation of the configured local or remote pharmacy server."""

from __future__ import annotations

import json
from typing import Any

from src.config import load_pharmacy_settings
from src.mcp.pharmacy import create_pharmacy_client
from src.mcp.protocol import JsonRpcResponseError


def main() -> int:
    """Validate discovery, every inventory tool, and both MCP error mechanisms."""

    settings = load_pharmacy_settings()
    print(f"Pharmacy transport: {settings.transport}")
    with create_pharmacy_client(settings=settings) as client:
        tools = client.list_tools()
        names = {tool["name"] for tool in tools}
        if names != {"get_medication_stock", "search_medications", "list_low_stock"}:
            raise RuntimeError("The server did not advertise the three expected pharmacy tools.")
        print("Pharmacy MCP tools:")
        print("\n".join(tool["name"] for tool in tools))
        print_result("get_medication_stock", client.call_tool("get_medication_stock", {"sku": "FAR-001"}))
        print_result("search_medications", client.call_tool("search_medications", {"query": "vitamin"}))
        print_result("list_low_stock", client.call_tool("list_low_stock", {"threshold": 10}))
        print_result("invalid SKU", client.call_tool("get_medication_stock", {"sku": "FAR-999"}))
        print_result("invalid threshold", client.call_tool("list_low_stock", {"threshold": -1}))
        try:
            client.call_tool("unknown_inventory_tool", {})
        except JsonRpcResponseError as error:
            if error.code != -32602:
                raise
            print(f"Unknown tool: expected JSON-RPC error {error.code}")
        else:
            raise RuntimeError("Unknown tools must produce a JSON-RPC error.")
    print("PASS: pharmacy MCP discovery, queries and error handling.")
    return 0


def print_result(label: str, result: Any) -> None:
    """Check the MCP result shape and expected outcome before displaying it."""

    expected_error = label in {"invalid SKU", "invalid threshold"}
    if not isinstance(result, dict) or result.get("isError") is not expected_error:
        raise RuntimeError(f"Unexpected tool outcome for {label}.")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError(f"{label} must return a structured JSON object.")
    content = result.get("content", [])
    if len(content) != 1 or json.loads(content[0]["text"]) != structured:
        raise RuntimeError(f"{label} returned inconsistent text and structured content.")
    print(f"{label} result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
