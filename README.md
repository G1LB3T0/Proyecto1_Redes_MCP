# CC3067 MCP Chatbot

## Project overview

This project is a console chatbot for the Networks course project. It uses the Gemini Developer API, preserves context only during the active session, and manually coordinates local MCP servers.

## Current features

- Initial project structure and dependency declaration.
- Safe loading and validation of Gemini environment variables.
- Configurable Gemini model selection.
- An interactive console chatbot using the Gemini Interactions API.
- Conversation context preserved in memory while the chatbot is running.
- Application logging for session events and safe API diagnostics.
- Manual JSON-RPC MCP client over stdio with request/response wire logging.
- Official Filesystem MCP Server restricted to `demo_workspace/`.
- Official Git MCP Server restricted to `demo_workspace/git_demo/`.
- Local manual Pharmacy Inventory MCP Server with demo-only stock data.

## Requirements

- Python 3.10 or newer
- A Gemini Developer API key from Google AI Studio
- Node.js, npm, and npx for the Filesystem MCP Server
- uv/uvx and Git for the Git MCP Server

## Installation

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Environment variables

Copy `.env.example` to `.env`, then set `GEMINI_API_KEY` locally. Do not commit or share `.env`.

`GEMINI_MODEL` is optional. If it is empty or not defined, the application uses `gemini-3.6-flash`.

## Running the chatbot

Start the chatbot:

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

To validate the local server without Gemini:

```powershell
python -m src.mcp.pharmacy_demo
```

For a chatbot demo, ask: `Search pharmacy items containing "vitamin" and tell me which ones have low stock.`

## Current limitations

- Conversation context is not persisted after the program closes.
- Each Gemini request has a 15-second timeout and one short automatic retry for timeout or server errors. Quota errors are not retried automatically.
- MCP servers are local stdio processes only; remote MCP, cloud deployment, Wireshark analysis, and a frontend are not implemented.
