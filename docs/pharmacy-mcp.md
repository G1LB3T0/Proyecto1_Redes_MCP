# Pharmacy Inventory MCP Server

## Purpose and industry use case

A pharmacy needs to answer stock questions and identify items that may need
replenishment. This MCP server gives the chatbot access to an inventory
snapshot so it can look up an exact SKU, search product names and identify low
stock. The chatbot obtains quantities from the server instead of inventing them.

The demonstration dataset contains nine products in
`data/pharmacy_inventory.json`. Quantities are fictional. The scope is inventory
visibility: there is no diagnosis, medication recommendation, sale or inventory
mutation. Changes to the JSON dataset become visible after restarting the server.
The project owner confirmed instructor approval of this case study.

This document specifies the shared tools and local transport. The
[remote deployment guide](deployment.md) documents requirement 6 and the HTTP
transport. Both execute the same dispatcher and inventory service.

## Components

| Component | File | Responsibility |
| --- | --- | --- |
| Inventory | `src/custom_mcp/inventory_service.py` | Loads and validates records; executes queries |
| Protocol | `src/custom_mcp/server_core.py` | Dispatches manual JSON-RPC/MCP messages |
| Transport | `src/custom_mcp/stdio_server.py` | Reads stdin and writes stdout, one JSON message per line |
| Remote transport | `src/custom_mcp/http_server.py` | Authenticated HTTP sessions over the same dispatcher |
| Client configuration | `src/mcp/pharmacy.py` | Selects stdio or HTTP from settings |
| Manual client | `src/mcp/stdio_client.py` | Initializes MCP, discovers and calls tools |
| Remote client | `src/mcp/http_client.py` | HTTPS, lifecycle, discovery, calls and session recovery |
| Host | `src/mcp/coordinator.py` | Maps Gemini function calls to MCP calls and returns results |
| Demo | `src/mcp/pharmacy_demo.py` | Checks all three tools and expected errors without Gemini |

The custom server and client use Python's standard library for MCP and JSON-RPC.
No MCP implementation library is imported. The Google GenAI SDK communicates
only with the LLM. The existing official Filesystem and Git servers are separate
dependencies of the full chatbot.

## Installation and execution

Use Python 3.10 or newer. Run commands from the repository root. For the full
chatbot on Windows, follow the README to install its Python dependencies, Node.js,
Git and uv, activate `.venv`, prepare the Git demo and configure `.env`.

The local stdio server itself needs no third-party Python packages and no
credentials. Select `PHARMACY_MCP_TRANSPORT=stdio` in `.env` for this check:

```powershell
python -m src.mcp.pharmacy_demo
```

Expected outcome: the three tool names, successful inventory results, expected
errors for an unknown SKU and invalid threshold, a JSON-RPC error for an unknown
tool, and a final `PASS` line. Requests and responses are recorded in
`logs/mcp.log` by the manual client.

To run just the server for another local MCP client:

```powershell
python -m src.custom_mcp.stdio_server
```

Configure that client with the project's virtual-environment Python executable,
arguments `-m src.custom_mcp.stdio_server`, and the repository root as its working
directory. The server waits for JSON-RPC input. It does not print an interactive
banner. Diagnostics use stderr; stdout contains protocol messages only. Closing
stdin ends the server.

## Protocol and local endpoint

| Property | Value |
| --- | --- |
| Server name / version | `pharmacy-inventory` / `0.2.0` |
| JSON-RPC version | `2.0` |
| Supported MCP version | `2025-11-25` |
| Transport | Local subprocess stdin/stdout; UTF-8, newline-delimited JSON |
| Endpoint | The process command above; there is no HTTP URL or listening port |
| Capability | `tools: {"listChanged": false}` |
| Request IDs | Strings or integers; each reply echoes its request ID |
| Notifications | No `id` and no response |
| Tool discovery | All three tools in one page; no pagination cursor |
| Data access | Read-only snapshot loaded at process startup |

Each JSON-RPC request occupies one physical line. The examples below can be sent
in order through stdin. Unknown notifications are ignored. JSON batches,
resources, prompts and other unadvertised capabilities are not offered. The
HTTP transport uses these same JSON bodies, without newline framing.

### Initialization

1. Send `initialize` before using the tools:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"example-client","version":"1.0"}}}
```

Expected response:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-11-25","capabilities":{"tools":{"listChanged":false}},"serverInfo":{"name":"pharmacy-inventory","version":"0.2.0"}}}
```

If a client requests a different version, the server returns its supported
version. The client must decide whether it can continue. `clientInfo.name`,
`clientInfo.version`, `protocolVersion` and `capabilities` are required.

2. Send the ready notification; there is no response:

```json
{"jsonrpc":"2.0","method":"notifications/initialized"}
```

Sending this notification before a successful `initialize` does not unlock the
tools. A second `initialize` on the same connection is rejected.

3. Discover the tool names, descriptions and input schemas:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
```

The response contains `result.tools`, an array with the three definitions below.
`ping` is supported before and after initialization and returns an empty object:

```json
{"jsonrpc":"2.0","id":"health","method":"ping"}
```

```json
{"jsonrpc":"2.0","id":"health","result":{}}
```

## Tool specification

All tool arguments are JSON objects. Unexpected argument names are rejected.
Required strings must contain a non-whitespace character; surrounding whitespace
is removed. Search and SKU matching are case-insensitive. Thresholds must be
non-negative integers; booleans, strings and fractional numbers are rejected.

| Tool | Arguments | Successful `structuredContent` |
| --- | --- | --- |
| `get_medication_stock` | Required `sku: string` | One product object |
| `search_medications` | Required `query: string`; substring of SKU or name | `{"items": [product, ...]}` |
| `list_low_stock` | Optional `threshold: integer`, default `10`, minimum `0` | `{"items": [product, ...]}` where `stock <= threshold` |

A product has `sku: string`, `name: string`, `stock: integer >= 0` and
`unit: string`. Results use dataset order. No matches produce `{"items": []}`.
An exact SKU lookup with no match is a tool error.

Each `tools/call` result has:

- `content`: one text block containing serialized JSON.
- `structuredContent`: that same data as a JSON object, including list results.
- `isError`: `false` for success or `true` for an inventory/input error.

### Example: look up stock

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_medication_stock","arguments":{"sku":"FAR-001"}}}
```

```json
{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"{\"sku\": \"FAR-001\", \"name\": \"Paracetamol 500 mg\", \"stock\": 48, \"unit\": \"boxes\"}"}],"structuredContent":{"sku":"FAR-001","name":"Paracetamol 500 mg","stock":48,"unit":"boxes"},"isError":false}}
```

### Example: search the inventory

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"search_medications","arguments":{"query":"vitamin"}}}
```

The result's `structuredContent` is:

```json
{"items":[{"sku":"FAR-004","name":"Vitamin C 1000 mg","stock":6,"unit":"bottles"},{"sku":"FAR-005","name":"Vitamin D3 1000 IU","stock":12,"unit":"bottles"}]}
```

### Example: identify low stock

```json
{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"list_low_stock","arguments":{"threshold":10}}}
```

The result contains four products: FAR-002 (8 boxes), FAR-004 (6 bottles), FAR-006
(4 boxes) and FAR-008 (9 packs). Omitting `threshold` gives the same result. A
threshold of `4` includes FAR-006, demonstrating the inclusive boundary.

## Errors and recovery

Protocol errors use the JSON-RPC `error` field. Tool execution errors use a
successful JSON-RPC envelope whose `result.isError` is `true`, so the model can
inspect and correct the request.

| Code / mechanism | Meaning |
| --- | --- |
| `-32700` | Malformed JSON, including NaN or Infinity; response ID is null |
| `-32600` | Invalid request envelope or unsupported request ID |
| `-32601` | Unknown JSON-RPC method |
| `-32602` | Invalid method parameters, unknown tool, repeated initialization or unsupported cursor |
| `-32002` | Tool operation before the initialization sequence finishes |
| `-32603` | Unexpected internal failure; valid request ID is preserved |
| `result.isError: true` | Unknown SKU, missing/invalid tool argument or unexpected argument |

An unknown tool produces a protocol error, for example:

```json
{"jsonrpc":"2.0","id":6,"error":{"code":-32602,"message":"Unknown inventory tool: missing_tool"}}
```

An unknown SKU produces a tool error:

```json
{"jsonrpc":"2.0","id":7,"result":{"content":[{"type":"text","text":"{\"error\": \"No pharmacy item exists for SKU FAR-999.\"}"}],"structuredContent":{"error":"No pharmacy item exists for SKU FAR-999."},"isError":true}}
```

The server stays available after recoverable input errors. A missing, malformed,
negative-stock or duplicate-SKU inventory dataset causes startup to fail instead
of serving ambiguous data. Restart after fixing the dataset.

## Chatbot demonstration

Start the full chatbot with the virtual environment activated and a valid local
`GEMINI_API_KEY`:

```powershell
python -m src.cli
```

Use these prompts in the same session:

1. `Use the pharmacy tools to look up FAR-001, search for vitamin, and list items with stock of 10 or less. Include SKUs and quantities.`
2. `Of the vitamins you found, which have stock of 10 or less?`
3. `Look up pharmacy SKU FAR-999.`
4. `/mcp-log`

Expected facts: FAR-001 has 48 boxes; the search finds FAR-004 and FAR-005; only
FAR-004 is a vitamin at or below the low-stock threshold; FAR-999 does not exist.
Natural-language phrasing may vary. Check the log for `server=pharmacy`,
`method=tools/call`, matching request/response IDs and the actual results.

The host exposes the names `pharmacy_get_medication_stock`,
`pharmacy_search_medications` and `pharmacy_list_low_stock` to Gemini to avoid
collisions with other servers. It translates them back to the MCP tool names,
executes calls through the configured transport and sends results to Gemini. Conversation history
retains tool calls, tool results and model replies for subsequent turns.

## Reproducible checks

```powershell
python -m unittest discover -s tests -v
python -m src.mcp.pharmacy_demo
```

The regression suite covers quantities and boundaries, validation, initialization
order, version negotiation, notifications, strict JSON, result formats, errors,
request IDs and real subprocess framing. Its chatbot integration test runs the
actual MCP process with a simulated model to check dispatch, history and failure
recovery. This automated test does not replace the real Gemini demonstration.

The client's wire log records actual protocol exchanges. It masks common
credential fields. `.env`, `.venv/`, logs and the demonstration workspace are
excluded from Git; the custom server, dataset, tests and this guide are the
deliverable source files.

### Verified outcomes

Validation was performed with Python 3.14.6 and `google-genai` 2.24.0:

- All 27 automated tests passed, including local HTTP transport integration.
- The standalone pharmacy demo passed, including both tool and protocol errors.
- The full chatbot connected to Filesystem, Git and Pharmacy MCP. A real Gemini
  session called all three pharmacy tools and returned the quantities above.
- A second turn correctly identified FAR-004 as the low-stock vitamin using the
  conversation context. A third turn called the stock tool for FAR-999 and
  reported that the SKU does not exist.
- The manual client's wire log confirmed the actual tool requests and replies.

The first live attempt exceeded the previous 15-second LLM timeout. Requests now
allow 60 seconds; the subsequent three-turn demonstration completed successfully.
API availability and account quota still depend on the Gemini service.

## Protocol references

- [MCP lifecycle and version negotiation](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [MCP tools and result/error formats](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [MCP ping](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping)
- [JSON-RPC 2.0](https://www.jsonrpc.org/specification)

These are protocol references. The custom MCP implementation is written directly
in this repository rather than copied from an MCP SDK.
