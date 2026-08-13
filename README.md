# CC3067 Phase 1 Chatbot

## Project overview

This project is a console chatbot for the first phase of the Networks course project. It will use the Gemini Developer API and keep conversation context only while the program is running.

## Current features

- Initial project structure and dependency declaration.

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

`GEMINI_MODEL` will be configurable by the application. Its default value will be `gemini-3.6-flash`.

## Running the chatbot

The console entry point will be added in the next checkpoints.

## Basic usage

The chatbot will not expose the API key.

## Current limitations

- No Gemini request is implemented yet.
- No interactive conversation or session context is implemented yet.
- No MCP functionality is implemented.
