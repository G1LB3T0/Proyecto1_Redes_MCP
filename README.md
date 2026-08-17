# CC3067 Phase 1 Chatbot

## Project overview

This project is a console chatbot for the first phase of the Networks course project. It will use the Gemini Developer API and keep conversation context only while the program is running.

## Current features

- Initial project structure and dependency declaration.
- Safe loading and validation of Gemini environment variables.
- Configurable Gemini model selection.
- An interactive console chatbot using the Gemini Interactions API.
- Conversation context preserved in memory while the chatbot is running.
- Application logging for session events and safe API diagnostics.

## Requirements

- Python 3.10 or newer
- A Gemini Developer API key from Google AI Studio

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

## Basic usage

The program accepts one prompt at a time and prints the model response without exposing the API key. It remembers prior turns only until the chatbot closes.

Application events are written to `logs/chatbot.log`. The log does not contain API keys or prompt text.

## Current limitations

- Conversation context is not persisted after the program closes.
- Each Gemini request has a 15-second timeout and one short automatic retry for timeout or server errors. Quota errors are not retried automatically.
- No MCP functionality is implemented.
