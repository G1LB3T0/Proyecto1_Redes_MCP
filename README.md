# CC3067 MCP Chatbot

## Project overview

This console chatbot for CC3067 Networks uses the Gemini Developer API, preserves
conversation context during the active session, and manually coordinates MCP
servers over local stdio and remote HTTPS. The industry case is a pharmacy
inventory with nine demonstration products.

## Current features

- Safe environment configuration and configurable Gemini model selection.
- An interactive console chatbot using the Gemini Interactions API.
- Conversation context preserved in memory while the chatbot is running.
- Application logging for session events and safe API diagnostics.
- Manual JSON-RPC MCP client over stdio with request/response wire logging.
- Official Filesystem MCP Server restricted to `demo_workspace/`.
- Official Git MCP Server restricted to `demo_workspace/git_demo/`.
- Local manual Pharmacy Inventory MCP Server with demo-only stock data.
- The same pharmacy server over authenticated Streamable HTTP, deployed on
  Hetzner behind Nginx and a verified TLS certificate.
- Isolated HTTP sessions, expiry/reconnection, input limits and error handling.
- Real network capture, message classification and a report in `docs/`.

## Requirements

- Windows client with Python 3.10 or newer
- A Gemini Developer API key from Google AI Studio
- Node.js, npm, and npx for the Filesystem MCP Server
- uv/uvx and Git for the Git MCP Server

## Installation

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pip install uv
```

## Environment variables

Copy `.env.example` to `.env`, then set `GEMINI_API_KEY` locally. Do not commit or share `.env`.

`GEMINI_MODEL` is optional. If it is empty or not defined, the application uses `gemini-3.1-flash-lite`.

The default pharmacy transport is `stdio`. To use the remote service, set:

```dotenv
PHARMACY_MCP_TRANSPORT=http
PHARMACY_MCP_URL=https://mcp.canchonfc.online/mcp
PHARMACY_MCP_TOKEN=<obtain privately from the server administrator>
```

The server token is distinct from your Gemini API key. The cloud server never
receives the Gemini key. The full client must have all three MCP servers available.

## Running the chatbot

The chatbot automatically initializes its isolated Git repository on first use.
To verify the official Filesystem and Git servers separately:

```powershell
python -m src.mcp.git_demo
```

This runs the official Filesystem and Git MCP servers, creates a demo README and
commits it inside `demo_workspace/git_demo/`. It does not commit changes to this
project. The Git client finds `uvx` beside the running Python executable, inside
the project's `.venv`, or on PATH, in that order. Activation is still recommended
so Python uses the project's installed dependencies.

Start the chatbot from the project root:

```powershell
python -m src.cli
```

Type `exit` to close the session.

Type `/mcp-log` inside the chatbot to display recent real MCP wire-log entries.

## Basic usage

The program accepts one prompt at a time and prints the model response without exposing the API key. It remembers prior turns only until the chatbot closes.

Application events are written to `logs/chatbot.log`. Real, sanitized MCP requests and responses are written to `logs/mcp.log`.

## MCP demo

The official Filesystem and Git servers operate only inside `demo_workspace/`; the main repository is never used as their sandbox.

The local Pharmacy Inventory MCP Server exposes `get_medication_stock`, `search_medications`, and `list_low_stock`. Its JSON dataset contains demonstration stock records only and does not provide medical advice.

To validate the configured pharmacy transport without Gemini:

```powershell
python -m src.mcp.pharmacy_demo
```

For a chatbot demo, ask: `Search pharmacy items containing "vitamin" and tell me which ones have low stock.`

The [Pharmacy MCP specification and usage guide](docs/pharmacy-mcp.md) documents
the industry use case, lifecycle, tool parameters, response formats, JSON-RPC
examples, errors and demonstration steps. See the [remote deployment guide](docs/deployment.md)
for HTTP endpoints, authentication, Docker isolation and operations.

The pharmacy server and manual client implement JSON-RPC directly using Python's
standard library. No MCP SDK or FastMCP is used in the custom implementation.
The Google SDK is used only for Gemini API access; the official Filesystem and
Git servers run as separate processes.

## Automated checks

Run the local regression and integration tests without an API key:

```powershell
python -m unittest discover -s tests -v
```

The 31 tests cover launcher discovery and launch real stdio and local HTTP
servers. They cover inventory, validation, lifecycle, authentication, sessions,
transport parity, errors and
chatbot orchestration. The model is simulated in automated tests.

Run a real six-turn Gemini demonstration (uses API quota and changes only the
isolated Git demo repository):

```powershell
python -m scripts.live_demo
```

It checks general questions, context, all pharmacy tools, an unknown SKU and a
Filesystem/Git commit. It saves the actual conversation in
`docs/evidence/live-demo.json`. Natural-language wording and tool order may vary.

## Submission material

- [Pharmacy tool specification](docs/pharmacy-mcp.md)
- [Remote transport and deployment](docs/deployment.md)
- [Network capture and packet analysis](docs/network-analysis.md)
- [Project report](docs/report.md)
- [Printable PDF report](output/pdf/Informe_Proyecto1_MCP.pdf)
- [Presentation and demonstration guide](docs/presentation.md)

Raw packet captures and TLS decryption keys stay under `logs/captures/` and are
excluded from Git. Sanitized packet metadata and JSON-RPC messages are included
as evidence. See the network guide to reproduce and open the capture in Wireshark.

To rebuild the printable report on Windows, install the optional authoring
dependency with `python -m pip install "reportlab>=4,<5"`, then run
`python scripts/build_report.py`. ReportLab is not required to run the chatbot.

## Current limitations

- Conversation context is not persisted after the program closes.
- Each Gemini request has a 60-second timeout and one short automatic retry for timeout or server errors. Quota errors are not retried automatically.
- The interface is a terminal. The optional graphical UI bonus is not implemented.
- Remote authentication uses a private static bearer token, not OAuth discovery.
- The HTTP server offers JSON responses, not a persistent/resumable SSE stream.
- HTTP session state is in memory in one worker; a restart triggers client reinitialization.
- The full chatbot expects all three MCP servers to be available. The standalone pharmacy demo and tests do not require Node.js, Git, uvx or a Gemini key.
- Official local server launch commands target Windows; the remote container runs Linux.
