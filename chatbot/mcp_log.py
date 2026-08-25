"""
Log de interacciones con los servidores MCP (funcionalidad 3).

Registra TODAS las solicitudes y respuestas que el anfitrion intercambia
con cada servidor MCP. Cada entrada se guarda en dos formatos:

  * En memoria y en logs/mcp_interactions.jsonl, una linea JSON por
    interaccion, para poder revisarlas despues.
  * En consola, en formato legible, para poder mostrarlas en vivo
    durante la demostracion.

Este log es distinto del log interno del servidor (logs/server.log):
aquel es la vista del servidor, este es la vista del anfitrion.
"""

import datetime
import json
import os
from typing import Any, Optional

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_PATH = os.path.join(LOG_DIR, "mcp_interactions.jsonl")

# Codigos ANSI para colorear la salida en consola.
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


class MCPLog:
    """Acumula y muestra las interacciones con los servidores MCP."""

    def __init__(self, echo: bool = True) -> None:
        self.entries: list[dict] = []
        self.echo = echo  # si True, imprime cada interaccion al ocurrir
        os.makedirs(LOG_DIR, exist_ok=True)

    def _write(self, entry: dict) -> None:
        self.entries.append(entry)
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            # Si el archivo no se puede escribir, el log en memoria sigue
            # funcionando y la sesion no se interrumpe.
            pass

    def request(self, server: str, message: dict) -> None:
        """Registra una solicitud enviada del anfitrion hacia un servidor."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "direction": "request",
            "server": server,
            "message": message,
        }
        self._write(entry)
        if self.echo:
            method = message.get("method", "?")
            msg_id = message.get("id", "-")
            print(f"{DIM}[MCP →] {server} #{msg_id} {method}{RESET}")

    def response(self, server: str, message: dict) -> None:
        """Registra una respuesta recibida de un servidor."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "direction": "response",
            "server": server,
            "message": message,
        }
        self._write(entry)
        if self.echo:
            msg_id = message.get("id", "-")
            if "error" in message:
                code = message["error"].get("code")
                print(f"{RED}[MCP ←] {server} #{msg_id} error {code}{RESET}")
            else:
                print(f"{DIM}[MCP ←] {server} #{msg_id} ok{RESET}")

    def notification(self, server: str, message: dict) -> None:
        """Registra una notificacion enviada (no espera respuesta)."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "direction": "notification",
            "server": server,
            "message": message,
        }
        self._write(entry)
        if self.echo:
            print(f"{DIM}[MCP →] {server} (notificacion) {message.get('method')}{RESET}")

    def show(self, last: Optional[int] = None) -> None:
        """Imprime el log completo o las ultimas `last` interacciones."""
        entries = self.entries if last is None else self.entries[-last:]
        if not entries:
            print("(el log de interacciones MCP esta vacio)")
            return

        print(f"\n{CYAN}=== Log de interacciones MCP ({len(entries)} entradas) ==={RESET}")
        for entry in entries:
            arrow = "→" if entry["direction"] != "response" else "←"
            print(f"\n{CYAN}[{entry['timestamp']}] {arrow} {entry['server']} "
                  f"({entry['direction']}){RESET}")
            print(json.dumps(entry["message"], indent=2, ensure_ascii=False))
        print()

    def summary(self) -> str:
        """Retorna un resumen de una linea del estado del log."""
        requests = sum(1 for e in self.entries if e["direction"] == "request")
        responses = sum(1 for e in self.entries if e["direction"] == "response")
        notifications = sum(1 for e in self.entries if e["direction"] == "notification")
        return (f"{len(self.entries)} interacciones "
                f"({requests} solicitudes, {responses} respuestas, "
                f"{notifications} notificaciones)")
