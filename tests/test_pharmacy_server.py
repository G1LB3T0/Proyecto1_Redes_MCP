"""Behavior and protocol regression tests for the manual pharmacy MCP server."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from src.custom_mcp.inventory_service import InventoryService
from src.custom_mcp.server_core import PharmacyMcpServer
from src.custom_mcp.stdio_server import _handle_line
from src.mcp.protocol import MCP_PROTOCOL_VERSION


ROOT = Path(__file__).resolve().parents[1]


def request(method: str, request_id: int | str = 1, **params: object) -> dict:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params:
        message["params"] = params
    return message


def initialize_message(**overrides: object) -> dict:
    params = {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    }
    params.update(overrides)
    return request("initialize", **params)


class InventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InventoryService()

    def test_stock_lookup_normalizes_sku_and_returns_copy(self) -> None:
        product = self.service.get_medication_stock({"sku": " far-001 "})
        self.assertEqual(product["stock"], 48)
        product["stock"] = 0
        self.assertEqual(self.service.get_medication_stock({"sku": "FAR-001"})["stock"], 48)

    def test_search_by_name_or_sku_and_empty_results(self) -> None:
        vitamins = self.service.search_medications({"query": " VITAMIN "})["items"]
        self.assertEqual([item["sku"] for item in vitamins], ["FAR-004", "FAR-005"])
        self.assertEqual(len(self.service.search_medications({"query": "far-001"})["items"]), 1)
        self.assertEqual(self.service.search_medications({"query": "not-in-inventory"}), {"items": []})

    def test_low_stock_default_and_inclusive_boundary(self) -> None:
        expected = ["FAR-002", "FAR-004", "FAR-006", "FAR-008"]
        self.assertEqual([item["sku"] for item in self.service.list_low_stock({})["items"]], expected)
        self.assertEqual(
            [item["sku"] for item in self.service.list_low_stock({"threshold": 4})["items"]],
            ["FAR-006"],
        )
        self.assertEqual(self.service.list_low_stock({"threshold": 0}), {"items": []})

    def test_invalid_inputs_are_rejected(self) -> None:
        cases = [
            ("get_medication_stock", {}),
            ("get_medication_stock", {"sku": 123}),
            ("search_medications", {"query": "  "}),
            ("search_medications", {"query": "vitamin", "unexpected": True}),
            ("list_low_stock", {"threshold": True}),
            ("list_low_stock", {"threshold": -1}),
            ("list_low_stock", {"threshold": 1.5}),
            ("list_low_stock", {"threshold": "10"}),
            ("list_low_stock", {"threshold": None}),
            ("list_low_stock", {"limit": 10}),
        ]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(ValueError):
                self.service.call_tool(name, arguments)

    def test_invalid_and_duplicate_inventory_records_fail_at_startup(self) -> None:
        product = {"sku": "FAR-001", "name": "Demo", "stock": 1, "unit": "boxes"}
        cases = [
            {},
            [dict(product, stock=-1)],
            [dict(product, stock=True)],
            [dict(product, name=" ")],
            [product, dict(product, sku=" far-001 ")],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            for data in cases:
                with self.subTest(data=data):
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaises(RuntimeError):
                        InventoryService(path)


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = PharmacyMcpServer()

    def initialize(self) -> None:
        result = self.server.handle(initialize_message())
        self.assertEqual(result["result"]["protocolVersion"], MCP_PROTOCOL_VERSION)
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_handshake_is_required_and_cannot_be_bypassed(self) -> None:
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(self.server.handle(request("tools/list"))["error"]["code"], -32002)
        self.server.handle(initialize_message())
        self.assertEqual(self.server.handle(request("tools/list"))["error"]["code"], -32002)
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized", "params": []})
        self.assertEqual(self.server.handle(request("tools/list"))["error"]["code"], -32002)
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(len(self.server.handle(request("tools/list"))["result"]["tools"]), 3)

    def test_version_negotiation_and_client_information(self) -> None:
        for params in ({"capabilities": None}, {"clientInfo": {}}, {"protocolVersion": 1}):
            with self.subTest(params=params):
                self.assertEqual(self.server.handle(initialize_message(**params))["error"]["code"], -32602)
        result = self.server.handle(initialize_message(protocolVersion="2099-01-01"))
        self.assertEqual(result["result"]["protocolVersion"], MCP_PROTOCOL_VERSION)
        self.assertEqual(self.server.handle(initialize_message())["error"]["code"], -32602)

    def test_ping_works_before_and_after_initialization(self) -> None:
        self.assertEqual(self.server.handle(request("ping", "ping-before")), {
            "jsonrpc": "2.0", "id": "ping-before", "result": {},
        })
        self.initialize()
        self.assertEqual(self.server.handle(request("ping"))["result"], {})

    def test_structured_results_are_objects_matching_text_content(self) -> None:
        self.initialize()
        cases = [
            ("get_medication_stock", {"sku": "FAR-001"}),
            ("search_medications", {"query": "vitamin"}),
            ("list_low_stock", {}),
            ("search_medications", {"query": "no-such-item"}),
        ]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=arguments):
                result = self.server.handle(request("tools/call", "call-1", name=name, arguments=arguments))["result"]
                self.assertFalse(result["isError"])
                self.assertIsInstance(result["structuredContent"], dict)
                self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])

    def test_missing_sku_and_invalid_inputs_are_tool_errors(self) -> None:
        self.initialize()
        for name, arguments in [
            ("get_medication_stock", {"sku": "FAR-999"}),
            ("list_low_stock", {"threshold": -1}),
            ("search_medications", {"query": "vitamin", "extra": True}),
        ]:
            with self.subTest(name=name):
                response = self.server.handle(request("tools/call", name=name, arguments=arguments))
                self.assertNotIn("error", response)
                self.assertTrue(response["result"]["isError"])
                self.assertIn("error", response["result"]["structuredContent"])

    def test_unknown_tool_and_malformed_calls_are_protocol_errors(self) -> None:
        self.initialize()
        for params in ({"name": "missing"}, {"name": ""}, {"name": "list_low_stock", "arguments": []}):
            with self.subTest(params=params):
                response = self.server.handle(request("tools/call", "bad-call", **params))
                self.assertEqual(response["id"], "bad-call")
                self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(self.server.handle(request("unknown"))["error"]["code"], -32601)
        self.assertEqual(self.server.handle(request("tools/list", cursor="fake"))["error"]["code"], -32602)

    def test_invalid_envelopes_and_notifications(self) -> None:
        for message in ([], None, 1, {}, {"jsonrpc": "1.0", "id": []}, request("ping", True), request("ping", [])):
            with self.subTest(message=message):
                response = self.server.handle(message)
                self.assertIsNone(response["id"])
                self.assertEqual(response["error"]["code"], -32600)
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "unknown"}))
        response = self.server.handle({"jsonrpc": "2.0", "id": 9, "method": "ping", "params": None})
        self.assertEqual(response["error"]["code"], -32602)

    def test_parse_errors_and_internal_error_keep_protocol_usable(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            for line in ('{', '{"jsonrpc":"2.0","id":NaN,"method":"ping"}'):
                response = _handle_line(self.server, line)
                self.assertEqual(response["error"]["code"], -32700)
            broken_server = Mock()
            broken_server.handle.side_effect = RuntimeError("private diagnostic")
            response = _handle_line(broken_server, json.dumps(request("ping", "original-id")))
        self.assertEqual(response["id"], "original-id")
        self.assertEqual(response["error"], {"code": -32603, "message": "Internal error"})
        self.assertEqual(_handle_line(self.server, json.dumps(request("ping")))["result"], {})

    def test_stdio_framing_recovery_and_exit_on_eof(self) -> None:
        lines = [
            "not json",
            json.dumps(initialize_message()),
            '{"jsonrpc":"2.0","method":"notifications/initialized"}',
            json.dumps(request("tools/call", "stock", name="get_medication_stock", arguments={"sku": "FAR-001"})),
            json.dumps(request("tools/call", "search", name="search_medications", arguments={"query": "rehydration"})),
            json.dumps(request("ping", "alive")),
        ]
        process = subprocess.run(
            [sys.executable, "-B", "-m", "src.custom_mcp.stdio_server"],
            input="\n".join(lines) + "\n", cwd=ROOT, capture_output=True,
            encoding="utf-8", timeout=10, check=True,
        )
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([response["id"] for response in responses], [None, 1, "stock", "search", "alive"])
        self.assertEqual(responses[2]["result"]["structuredContent"]["stock"], 48)
        self.assertEqual(responses[3]["result"]["structuredContent"]["items"][0]["sku"], "FAR-007")
        self.assertEqual(responses[-1]["result"], {})
        self.assertIn("invalid JSON-RPC input", process.stderr)


if __name__ == "__main__":
    unittest.main()
