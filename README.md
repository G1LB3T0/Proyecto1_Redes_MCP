# CC3067 Phase 1 Chatbot

## Project overview

This project is a console chatbot for the first phase of the Networks course project. It will use the Gemini Developer API and keep conversation context only while the program is running.

## Current features

- Initial project structure and dependency declaration.
- Safe loading and validation of Gemini environment variables.
- Configurable Gemini model selection.
- A one-request console test using the Gemini Interactions API.

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

Send one prompt to Gemini:

```powershell
python -m src.cli "Reply only with: FASE1_API_OK"
```

The interactive chatbot will be added in later checkpoints.

## Basic usage

The program prints the model response without exposing the API key.

## Current limitations

- No interactive conversation or session context is implemented yet.
- No MCP functionality is implemented.
