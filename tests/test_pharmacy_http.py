"""Real HTTP exchanges covering MCP sessions, access checks and transport parity."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

from src.chatbot_core import ChatbotCore
from src.config import ConfigurationError, PharmacySettings, load_pharmacy_settings
from src.custom_mcp.http_server import PharmacyHttpApp
from src.llm_client import GeminiInteraction
from src.mcp.coordinator import McpCoordinator, McpServerBinding
from src.mcp.http_client import HttpMcpClient
from src.mcp.logging import McpWireLogger
from src.mcp.pharmacy import create_pharmacy_client
from src.mcp.protocol import MCP_PROTOCOL_VERSION, JsonRpcResponseError
from src.mcp.stdio_client import McpTransportError


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = PharmacyHttpApp("unit-test-token", allowed_origins=("https://example.test",))
        cls.server = make_server("127.0.0.1", 0, cls.app, handler_class=QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/mcp"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.app._sessions.clear()
        self.wire = Mock(spec=McpWireLogger)

    def client(self):
        return HttpMcpClient(url=self.url, auth_token="unit-test-token", wire_logger=self.wire)

    def raw(self, body=None, *, method="POST", path="/mcp", headers=None):
        defaults = {"Authorization": "Bearer unit-test-token", "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": MCP_PROTOCOL_VERSION}
        defaults.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=defaults)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_http_and_stdio_return_identical_results(self):
        with self.client() as remote, create_pharmacy_client() as local:
            self.assertEqual(remote.list_tools(), local.list_tools())
            for name, args in [
                ("get_medication_stock", {"sku": "far-001"}),
                ("search_medications", {"query": "vitamin"}),
                ("list_low_stock", {"threshold": 10}),
                ("get_medication_stock", {"sku": "FAR-999"}),
                ("list_low_stock", {"threshold": -1}),
            ]:
                with self.subTest(name=name, args=args):
                    self.assertEqual(remote.call_tool(name, args), local.call_tool(name, args))
        self.assertEqual(len(self.app._sessions), 0)
        records = [call.kwargs for call in self.wire.record.call_args_list]
        self.assertTrue(all(record["transport"] == "http" for record in records))
        self.assertNotIn("unit-test-token", json.dumps(records))

    def test_unknown_tools_remain_json_rpc_errors(self):
        with self.client() as client:
            with self.assertRaises(JsonRpcResponseError) as caught:
                client.call_tool("nonexistent", {})
            self.assertEqual(caught.exception.code, -32602)
            self.assertEqual(len(client.list_tools()), 3)

    def test_isolated_sessions_and_automatic_reinitialization(self):
        with self.client() as first, self.client() as second:
            original = first._session_id
            self.assertNotEqual(original, second._session_id)
            del self.app._sessions[original]
            self.assertEqual(len(first.list_tools()), 3)
            self.assertNotEqual(original, first._session_id)
            self.assertEqual(len(second.list_tools()), 3)

    def test_expired_sessions_are_replaced(self):
        with self.client() as client:
            old = client._session_id
            self.app._sessions[old].last_seen = -100000
            self.assertEqual(len(client.list_tools()), 3)
            self.assertNotEqual(client._session_id, old)

    def test_authentication_and_origin_validation(self):
        status, headers, _ = self.raw("{}", headers={"Authorization": "Bearer incorrect"})
        self.assertEqual(status, 401)
        self.assertIn("WWW-Authenticate", headers)
        self.assertEqual(self.raw("{}", headers={"Origin": "https://untrusted.test"})[0], 403)
        with self.assertRaises(McpTransportError):
            HttpMcpClient(url=self.url, auth_token="wrong", wire_logger=self.wire).connect()

    def test_supported_http_methods_health_and_content_types(self):
        self.assertEqual(self.raw(method="GET", path="/healthz", headers={"Authorization": ""})[0], 200)
        self.assertEqual(self.raw(method="GET")[0], 405)
        self.assertEqual(self.raw(method="DELETE")[0], 400)
        self.assertEqual(self.raw("{}", path="/other")[0], 404)
        self.assertEqual(self.raw("{}", headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.raw("{}", headers={"Accept": "application/json"})[0], 406)
        self.assertEqual(self.raw("{}", headers={"MCP-Protocol-Version": "wrong"})[0], 400)

    def test_malformed_bodies_and_missing_sessions(self):
        for body in ("not json", '{"id":NaN}'):
            status, _, response = self.raw(body)
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(response)["error"]["code"], -32700)
        self.assertEqual(self.raw("[]")[0], 400)
        self.assertEqual(self.raw("x" * 65537)[0], 413)
        self.assertEqual(self.raw('{"jsonrpc":"2.0","id":1,"method":"tools/list"}')[0], 400)
        self.assertEqual(self.raw("{}", headers={"MCP-Session-Id": "missing"})[0], 404)

    def test_ready_notification_has_empty_202_response(self):
        initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
        status, headers, response = self.raw(json.dumps(initialize))
        self.assertEqual(status, 200)
        session_id = headers["MCP-Session-Id"]
        headers = {"MCP-Session-Id": session_id}
        status, _, response = self.raw('{"jsonrpc":"2.0","id":2,"method":"tools/list"}', headers=headers)
        self.assertEqual(json.loads(response)["error"]["code"], -32002)
        status, _, body = self.raw('{"jsonrpc":"2.0","method":"notifications/initialized"}', headers=headers)
        self.assertEqual((status, body), (202, b""))
        status, _, body = self.raw(method="DELETE", headers=headers)
        self.assertEqual((status, body), (204, b""))

    def test_capacity_does_not_evict_active_sessions(self):
        with patch.object(self.app, "_max_sessions", 1), self.client() as first:
            with self.assertRaises(McpTransportError):
                self.client().connect()
            self.assertEqual(len(first.list_tools()), 3)

    def test_sse_post_response_is_understood(self):
        client = self.client()
        response = {"jsonrpc": "2.0", "id": 7, "result": {"tools": []}}
        stream = 'id: event-1\ndata:\n\nevent: message\ndata: ' + json.dumps(response) + '\n\n'
        self.assertEqual(client._sse_response(stream, "tools/list", 7), response)

    def test_remote_url_and_configuration_validation(self):
        for url in ("http://example.test/mcp", "https://user:pass@example.test/mcp", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                HttpMcpClient(url=url, auth_token="test", wire_logger=self.wire)
        with patch("src.config.load_dotenv"), patch.dict("os.environ", {"PHARMACY_MCP_TRANSPORT": "invalid"}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_pharmacy_settings()
        settings = PharmacySettings("http", self.url, "do-not-display")
        self.assertNotIn("do-not-display", repr(settings))

    def test_chatbot_dispatches_to_real_http_server_and_keeps_context(self):
        model = Mock()
        model.interact.side_effect = [
            GeminiInteraction(None, "1", ({"type": "function_call", "id": "stock", "name": "pharmacy_get_medication_stock", "arguments": {"sku": "FAR-001"}},)),
            GeminiInteraction("48 boxes", "2", ({"type": "model_output", "content": [{"type": "text", "text": "48 boxes"}]},)),
            GeminiInteraction("Same product", "3", ({"type": "model_output", "content": [{"type": "text", "text": "Same product"}]},)),
        ]
        chatbot = ChatbotCore(model, McpCoordinator((McpServerBinding("pharmacy", self.client()),)))
        try:
            self.assertEqual(chatbot.send_message("Stock FAR-001"), "48 boxes")
            chatbot.send_message("Which product?")
            history = model.interact.call_args_list[-1].args[0]
            result = next(step for step in history if step["type"] == "function_result")
            self.assertEqual(json.loads(result["result"])["structuredContent"]["stock"], 48)
        finally:
            chatbot.close()


if __name__ == "__main__":
    unittest.main()
