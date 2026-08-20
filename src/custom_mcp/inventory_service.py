"""Demo-only pharmacy inventory data and MCP tool logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INVENTORY_FILE = Path(__file__).resolve().parents[2] / "data" / "pharmacy_inventory.json"


class InventoryService:
    """Provide read-only pharmacy stock queries over local demonstration data."""

    def __init__(self, inventory_file: Path = INVENTORY_FILE) -> None:
        self._products = _load_products(inventory_file)

    def tools(self) -> list[dict[str, Any]]:
        """Return the MCP tools and schemas offered by this local server."""

        return [
            {
                "name": "get_medication_stock",
                "description": "Get current stock for one pharmacy item by SKU.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"sku": {"type": "string"}},
                    "required": ["sku"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "search_medications",
                "description": "Search pharmacy inventory by SKU or product name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "list_low_stock",
                "description": "List pharmacy items with stock at or below a threshold.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"threshold": {"type": "integer", "minimum": 0}},
                    "additionalProperties": False,
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute one validated inventory query."""

        if name == "get_medication_stock":
            return self.get_medication_stock(arguments)
        if name == "search_medications":
            return self.search_medications(arguments)
        if name == "list_low_stock":
            return self.list_low_stock(arguments)
        raise LookupError(f"Unknown inventory tool: {name}")

    def get_medication_stock(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return one item matching an exact SKU."""

        sku = _required_string(arguments, "sku").upper()
        for product in self._products:
            if product["sku"] == sku:
                return dict(product)
        raise LookupError(f"No pharmacy item exists for SKU {sku}.")

    def search_medications(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        """Return products whose SKU or name contains the supplied query."""

        query = _required_string(arguments, "query").casefold()
        return [
            dict(product)
            for product in self._products
            if query in product["sku"].casefold() or query in product["name"].casefold()
        ]

    def list_low_stock(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        """Return items whose stock is at or below the requested threshold."""

        threshold = arguments.get("threshold", 10)
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 0:
            raise ValueError("threshold must be a non-negative integer.")
        return [dict(product) for product in self._products if product["stock"] <= threshold]


def _load_products(inventory_file: Path) -> tuple[dict[str, Any], ...]:
    try:
        raw_products = json.loads(inventory_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not load pharmacy demo inventory: {error}") from error
    if not isinstance(raw_products, list):
        raise RuntimeError("Pharmacy demo inventory must be a JSON array.")

    products: list[dict[str, Any]] = []
    required_fields = {"sku", "name", "stock", "unit"}
    for product in raw_products:
        if not isinstance(product, dict) or set(product) != required_fields:
            raise RuntimeError("Pharmacy demo inventory contains an invalid product.")
        if (
            not isinstance(product["sku"], str)
            or not isinstance(product["name"], str)
            or isinstance(product["stock"], bool)
            or not isinstance(product["stock"], int)
            or product["stock"] < 0
            or not isinstance(product["unit"], str)
        ):
            raise RuntimeError("Pharmacy demo inventory contains invalid field values.")
        products.append(dict(product))
    return tuple(products)


def _required_string(arguments: dict[str, Any], field: str) -> str:
    value = arguments.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value.strip()
