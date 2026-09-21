"""Exercise the real local MCP process through the host without a paid LLM call."""

from __future__ import annotations

import json
import sys
import unittest
from unittest.mock import Mock

from src.chatbot_core import ChatbotCore, ChatbotCoreError
from src.llm_client import GeminiInteraction, GeminiRequestError
from src.mcp.coordinator import McpCoordinator, McpServerBinding
from src.mcp.logging import McpWireLogger
from src.mcp.stdio_client import StdioMcpClient


class ChatbotIntegrationTests(unittest.TestCase):
    def test_tool_results_context_errors_and_wire_messages(self) -> None:
        wire = Mock(spec=McpWireLogger)
        mcp_client = StdioMcpClient(
            server_name="pharmacy", command=(sys.executable, "-B", "-m", "src.custom_mcp.stdio_server"),
            wire_logger=wire,
        )
        model = Mock()
        chatbot = ChatbotCore(model, McpCoordinator((McpServerBinding("pharmacy", mcp_client),)))
        received_history = []

        def interact(history, tools, system_instruction=None):
            received_history.append(list(history))
            names = {tool["name"] for tool in tools}
            self.assertIn("pharmacy_search_medications", names)
            if len(received_history) == 1:
                return GeminiInteraction(None, "mock-1", ({
                    "type": "function_call", "id": "search-1", "name": "pharmacy_search_medications",
                    "arguments": {"query": "vitamin"},
                },))
            if len(received_history) == 2:
                result = history[-1]
                self.assertEqual(result["call_id"], "search-1")
                self.assertFalse(result["is_error"])
                self.assertEqual(len(json.loads(result["result"])["structuredContent"]["items"]), 2)
            text = "Two vitamin products." if len(received_history) == 2 else "The previous results are still available."
            return GeminiInteraction(text, "mock-response", ({
                "type": "model_output", "content": [{"type": "text", "text": text}],
            },))

        model.interact.side_effect = interact
        try:
            self.assertEqual(chatbot.send_message("Search vitamin"), "Two vitamin products.")
            chatbot.send_message("Which items were those?")
            followup_history = received_history[-1]
            self.assertTrue(any(step["type"] == "function_result" for step in followup_history))
            self.assertTrue(any(step["type"] == "model_output" for step in followup_history))
            model.interact.side_effect = GeminiRequestError("Simulated network failure")
            with self.assertRaises(ChatbotCoreError):
                chatbot.send_message("Discard this failed turn")
            model.interact.side_effect = interact
            chatbot.send_message("Resume")
            self.assertNotIn("Discard this failed turn", json.dumps(received_history[-1]))
        finally:
            chatbot.close()
        model.close.assert_called_once()
        records = [call.kwargs for call in wire.record.call_args_list]
        requests = [record for record in records if record["direction"] == "CLIENT->SERVER"]
        self.assertEqual([record["method"] for record in requests], [
            "initialize", "notifications/initialized", "tools/list", "tools/call",
        ])
        replies = [record for record in records if record["direction"] == "SERVER->CLIENT"]
        self.assertEqual(len(replies), 3)
        self.assertTrue(all(record["transport"] == "stdio" for record in records))


if __name__ == "__main__":
    unittest.main()
