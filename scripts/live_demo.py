"""Run the real chatbot demonstration and save a credential-free transcript.

Run from the project root with: python -m scripts.live_demo
This consumes Gemini API quota and creates one commit only in demo_workspace.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

from src.app_logging import configure_logging
from src.chatbot_core import create_demo_chatbot
from src.config import load_settings
from src.mcp.git_demo import GIT_DEMO_REPOSITORY


def main() -> None:
    configure_logging()
    settings = load_settings()
    started = datetime.now(timezone.utc).isoformat()
    prompts = [
        "Responde brevemente: ¿quién fue Alan Turing?",
        "¿En qué fecha nació la persona de mi pregunta anterior?",
        'Usa las herramientas de farmacia para consultar FAR-001, buscar "vitamin" '
        'y listar productos con stock menor o igual a 10. Incluye SKU y cantidades.',
        "De las vitaminas que encontraste, ¿cuál tiene stock de 10 o menos?",
        "Consulta el SKU FAR-999 usando la herramienta de farmacia.",
        f'Usa Filesystem MCP para escribir el archivo '
        f'{GIT_DEMO_REPOSITORY / "README.md"} con el texto "Demostración MCP: '
        f'Filesystem y Git. Ejecución {started}". Usa Git MCP para agregar README.md, '
        'hacer un commit con el mensaje "docs: demonstrate chatbot MCP tools" '
        'y mostrar el último commit. Opera solo dentro del repositorio de demostración.',
    ]
    transcript = {"started_utc": started, "model": settings.model,
                  "pharmacy_transport": settings.pharmacy.transport, "turns": []}
    output = Path("docs/evidence/live-demo.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    chatbot = create_demo_chatbot(settings)
    try:
        for prompt in prompts:
            print("USER:", prompt, flush=True)
            response = chatbot.send_message(prompt)
            print("ASSISTANT:", response, flush=True)
            transcript["turns"].append({"prompt": prompt, "response": response})
            output.write_text(json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        chatbot.close()
    print("Completed real chatbot demonstration:", output, flush=True)


if __name__ == "__main__":
    main()
