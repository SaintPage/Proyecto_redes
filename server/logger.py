"""
Utilidad de logging.

Cada registro de log va a stderr y a logs/server.log, NUNCA a stdout,
porque stdout transporta los frames de JSON-RPC.

El chatbot anfitrion tiene su propio log separado para el requisito 3
(mostrar todas las interacciones con los servidores MCP); este es la
vista del lado del servidor, muy util para depurar el handshake.
"""

import logging
import os
import sys

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")


def get_logger(name: str = "mcp-server") -> logging.Logger:
    """Retorna un logger que escribe a stderr y a logs/server.log."""
    logger = logging.getLogger(name)
    if logger.handlers:  # ya esta configurado
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
        # Si no se puede abrir el archivo de log, igual mantenemos el
        # logging por stderr.
        pass

    return logger