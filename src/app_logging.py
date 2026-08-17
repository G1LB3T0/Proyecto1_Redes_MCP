"""Application logging configuration for the console chatbot."""

from __future__ import annotations

import logging
from pathlib import Path


APP_LOGGER_NAME = "chatbot"
LOG_DIRECTORY = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIRECTORY / "chatbot.log"


def configure_logging() -> logging.Logger:
    """Configure a file logger without recording secrets or prompt content."""

    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    LOG_DIRECTORY.mkdir(exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger
