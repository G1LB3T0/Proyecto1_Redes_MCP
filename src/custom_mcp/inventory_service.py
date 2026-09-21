"""Demo-only pharmacy inventory data and MCP tool logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INVENTORY_FILE = Path(__file__).resolve().parents[2] / "data" / "pharmacy_inventory.json"


class UnknownToolError(LookupError):
    """Separate tool discovery errors from missing inventory records."""


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
                    "properties": {"sku": {"type": "string", "minLength": 1}},
                    "required": ["sku"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "search_medications",
                "description": "Search pharmacy inventory by SKU or product name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "minLength": 1}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "list_low_stock",
                "description": "List pharmacy items with stock at or below a threshold.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "integer", "minimum": 0, "default": 10}
                    },
                    "additionalProperties": False,
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute one validated inventory query."""

        if name == "get_medication_stock":
            return self.get_medication_stock(arguments)
        if name == "search_medications":
            return self.search_medications(arguments)
        if name == "list_low_stock":
            return self.list_low_stock(arguments)
        raise UnknownToolError(f"Unknown inventory tool: {name}")

    def get_medication_stock(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return one item matching an exact SKU."""

        _validate_keys(arguments, {"sku"})
        sku = _required_string(arguments, "sku").upper()
        for product in self._products:
            if product["sku"] == sku:
                return dict(product)
        raise LookupError(f"No pharmacy item exists for SKU {sku}.")

    def search_medications(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return products whose SKU or name contains the supplied query."""

        _validate_keys(arguments, {"query"})
        query = _required_string(arguments, "query").casefold()
        products = [
            dict(product)
            for product in self._products
            if query in product["sku"].casefold() or query in product["name"].casefold()
        ]
        return {"items": products}

    def list_low_stock(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Return items whose stock is at or below the requested threshold."""

        _validate_keys(arguments, {"threshold"})
        threshold = arguments.get("threshold", 10)
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 0:
            raise ValueError("threshold must be a non-negative integer.")
        return {
            "items": [dict(product) for product in self._products if product["stock"] <= threshold]
        }


def _load_products(inventory_file: Path) -> tuple[dict[str, Any], ...]:
    try:
        raw_products = json.loads(inventory_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not load pharmacy demo inventory: {error}") from error
    if not isinstance(raw_products, list):
        raise RuntimeError("Pharmacy demo inventory must be a JSON array.")

    products: list[dict[str, Any]] = []
    seen_skus: set[str] = set()
    required_fields = {"sku", "name", "stock", "unit"}
    for product in raw_products:
        if not isinstance(product, dict) or set(product) != required_fields:
            raise RuntimeError("Pharmacy demo inventory contains an invalid product.")
        if (
            not isinstance(product["sku"], str)
            or not product["sku"].strip()
            or not isinstance(product["name"], str)
            or not product["name"].strip()
            or isinstance(product["stock"], bool)
            or not isinstance(product["stock"], int)
            or product["stock"] < 0
            or not isinstance(product["unit"], str)
            or not product["unit"].strip()
        ):
            raise RuntimeError("Pharmacy demo inventory contains invalid field values.")
        product = dict(product)
        product["sku"] = product["sku"].strip().upper()
        if product["sku"] in seen_skus:
            raise RuntimeError("Pharmacy demo inventory contains duplicate SKUs.")
        seen_skus.add(product["sku"])
        products.append(dict(product))
    return tuple(products)


def _required_string(arguments: dict[str, Any], field: str) -> str:
    value = arguments.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value.strip()


def _validate_keys(arguments: dict[str, Any], allowed: set[str]) -> None:
    """Enforce additionalProperties: false without an MCP or schema SDK."""

    unexpected = set(arguments).difference(allowed)
    if unexpected:
        raise ValueError("Unexpected arguments: " + ", ".join(sorted(unexpected)))
