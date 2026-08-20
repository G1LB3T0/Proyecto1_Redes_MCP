"""Manual, Gemini-free validation of the local pharmacy MCP server."""

from __future__ import annotations

import json
from typing import Any

from src.mcp.pharmacy import create_pharmacy_client


def main() -> int:
    """Exercise every pharmacy inventory tool and one expected error case."""

    with create_pharmacy_client() as client:
        tools = client.list_tools()
        print("Pharmacy MCP tools:")
        print("\n".join(tool["name"] for tool in tools))
        print_result("get_medication_stock", client.call_tool("get_medication_stock", {"sku": "FAR-001"}))
        print_result("search_medications", client.call_tool("search_medications", {"query": "vitamin"}))
        print_result("list_low_stock", client.call_tool("list_low_stock", {"threshold": 10}))
        print_result("invalid SKU", client.call_tool("get_medication_stock", {"sku": "FAR-999"}))
    return 0


def print_result(label: str, result: Any) -> None:
    """Print one unmodified MCP tool result."""

    print(f"{label} result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
