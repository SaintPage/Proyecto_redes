"""
Transporte stdio para MCP.

MCP sobre stdio utiliza JSON delimitado por saltos de linea: cada
mensaje es un objeto JSON en una sola linea, terminado por "\\n". Los
mensajes NO deben contener saltos de linea embebidos.

IMPORTANTE: stdout es un canal de protocolo. Cualquier cosa impresa ahi
que no sea un mensaje JSON-RPC valido corrompe el stream y rompe al
cliente. Todo el diagnostico va a stderr en su lugar (ver logger.py).

Esta clase es intencionalmente pequena para que la Parte 2 del proyecto
pueda cambiarla por un transporte HTTP sin tocar la logica de protocolo.
"""

import json
import sys
from typing import Iterator, Optional


class StdioTransport:
    """Lee y escribe JSON delimitado por saltos de linea sobre stdin/stdout."""

    def __init__(self, stdin=None, stdout=None) -> None:
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout

    def receive(self) -> Iterator[tuple[Optional[dict], Optional[str]]]:
        """
        Genera pares (mensaje, error), uno por cada linea entrante.

        Si una linea no es JSON valido, `message` es None y `error`
        contiene la razon, para que quien llama pueda responder con un
        error -32700 (Parse error). Las lineas en blanco se ignoran.
        """
        for line in self._stdin:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), None
            except json.JSONDecodeError as exc:
                yield None, str(exc)

    def send(self, message: dict) -> None:
        """Serializa y escribe un mensaje, luego hace flush de inmediato."""
        # separators sin espacios mantiene el frame compacto;
        # ensure_ascii=False permite enviar acentos sin escaparlos.
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
        self._stdout.write(data + "\n")
        self._stdout.flush()  # sin esto el cliente se queda esperando