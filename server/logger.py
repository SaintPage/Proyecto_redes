"""
Logging helper.

Every log record goes to stderr and to logs/server.log, NEVER to stdout,
because stdout carries the JSON-RPC frames.

The chatbot host has its own separate log for requirement 3 (showing all
interactions with MCP servers); this one is the server-side view, which
is very useful when debugging the handshake.
"""

import logging
import os
import sys

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def get_logger(name: str = "mcp-server") -> logging.Logger:
    """Return a logger writing to stderr and to logs/server.log."""
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = logging.FileHandler(
            os.path.join(LOG_DIR, "server.log"), encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        # If the log file cannot be opened we still keep stderr logging.
        pass

    return logger
