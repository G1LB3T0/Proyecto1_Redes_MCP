"""Manual, Gemini-free validation of the official Filesystem MCP server."""

from __future__ import annotations

import json

from src.mcp.filesystem import DEMO_WORKSPACE, create_filesystem_client


DEMO_FILE = DEMO_WORKSPACE / "filesystem_mcp_demo.txt"
DEMO_CONTENT = "CC3067 Filesystem MCP demo\n"
REQUIRED_TOOLS = {"write_file", "read_file"}


def main() -> int:
    """List tools, then write and read a file through real MCP requests."""

    with create_filesystem_client() as client:
        tools = client.list_tools()
        tool_names = sorted(
            tool["name"] for tool in tools if isinstance(tool.get("name"), str)
        )
        print("Filesystem MCP tools:")
        print("\n".join(tool_names))

        missing_tools = REQUIRED_TOOLS.difference(tool_names)
        if missing_tools:
            raise RuntimeError(
                "Filesystem MCP did not advertise required tools: "
                + ", ".join(sorted(missing_tools))
            )

        write_result = client.call_tool(
            "write_file", {"path": str(DEMO_FILE), "content": DEMO_CONTENT}
        )
        read_result = client.call_tool("read_file", {"path": str(DEMO_FILE)})

    print("write_file result:")
    print(json.dumps(write_result, ensure_ascii=False, indent=2))
    print("read_file result:")
    print(json.dumps(read_result, ensure_ascii=False, indent=2))
    print(f"Demo file: {DEMO_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
