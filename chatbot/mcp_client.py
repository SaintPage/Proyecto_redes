"""
Cliente MCP implementado a mano sobre JSON-RPC 2.0.

Es el espejo del servidor: en vez de recibir mensajes y responder, este
modulo lanza un servidor MCP como subproceso, le ENVIA mensajes por su
stdin y LEE sus respuestas por su stdout.

Reutiliza server/jsonrpc.py, la misma capa de formato que usa el
servidor, para no duplicar la logica de JSON-RPC. No se usa ningun SDK
de MCP, tal como exige el enunciado.

Funciona con cualquier servidor MCP que hable por stdio: el servidor de
farmacia propio, y mas adelante los servidores oficiales de Filesystem
y Git.
"""

import json
import subprocess
import sys
from typing import Any, Optional

sys.path.insert(0, __file__.rsplit("chatbot", 1)[0])

from server import jsonrpc  # noqa: E402
from .mcp_log import MCPLog  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "pharmacy-chatbot", "version": "0.1.0"}


class MCPClientError(Exception):
    """Error al comunicarse con un servidor MCP."""


class MCPClient:
    """
    Mantiene la conexion con UN servidor MCP.

    El anfitrion (chatbot) puede tener varios clientes, uno por servidor,
    tal como describe la arquitectura de MCP.
    """

    def __init__(self, name: str, command: list[str], log: MCPLog) -> None:
        self.name = name          # nombre corto para el log, ej. "pharmacy"
        self.command = command    # comando que lanza el servidor
        self.log = log
        self.process: Optional[subprocess.Popen] = None
        self.tools: list[dict] = []
        self._next_id = 1

    # ciclo de vida 

    def start(self) -> None:
        """Lanza el servidor como subproceso y completa el handshake."""
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # El stderr del servidor es su log interno; se descarta para
            # que no se mezcle con la conversacion del chatbot.
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,  # linea por linea
        )

        # Paso 1: initialize
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })

        # Paso 2: notifications/initialized (sin respuesta)
        self._notify("notifications/initialized")

        # Paso 3: tools/list
        tools_result = self._request("tools/list")
        self.tools = tools_result.get("tools", [])

        return result

    def stop(self) -> None:
        """Cierra el subproceso del servidor."""
        if self.process is None:
            return
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            self.process.kill()
        self.process = None

    # -- envio de mensajes -----------------------------------------------

    def _send(self, message: dict) -> None:
        """Escribe un mensaje JSON-RPC al stdin del servidor."""
        if self.process is None or self.process.stdin is None:
            raise MCPClientError(f"El servidor '{self.name}' no esta activo")
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
        self.process.stdin.write(data + "\n")
        self.process.stdin.flush()

    def _read(self) -> dict:
        """Lee una linea de respuesta del stdout del servidor."""
        if self.process is None or self.process.stdout is None:
            raise MCPClientError(f"El servidor '{self.name}' no esta activo")
        line = self.process.stdout.readline()
        if not line:
            raise MCPClientError(
                f"El servidor '{self.name}' cerro la conexion inesperadamente"
            )
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise MCPClientError(
                f"Respuesta invalida de '{self.name}': {exc}"
            ) from exc

    def _request(self, method: str, params: Optional[dict] = None) -> dict:
        """
        Envia una solicitud y espera su respuesta.

        Toda solicitud y toda respuesta quedan registradas en el log
        (funcionalidad 3 del proyecto).
        """
        message: dict[str, Any] = {
            "jsonrpc": jsonrpc.JSONRPC_VERSION,
            "id": self._next_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._next_id += 1

        self.log.request(self.name, message)
        self._send(message)

        response = self._read()
        self.log.response(self.name, response)

        if "error" in response:
            error = response["error"]
            raise MCPClientError(
                f"{self.name}: error {error.get('code')} - {error.get('message')}"
            )
        return response.get("result", {})

    def _notify(self, method: str, params: Optional[dict] = None) -> None:
        """Envia una notificacion. Por especificacion, no espera respuesta."""
        message: dict[str, Any] = {
            "jsonrpc": jsonrpc.JSONRPC_VERSION,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        self.log.notification(self.name, message)
        self._send(message)

    # -- uso de herramientas ---------------------------------------------

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[str, bool]:
        """
        Ejecuta una tool en el servidor.

        Retorna (texto_del_resultado, hubo_error). Los errores de
        ejecucion de la tool llegan dentro del resultado con
        isError=true, no como errores de JSON-RPC.
        """
        result = self._request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        blocks = result.get("content", [])
        text = "\n".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        )
        return text, bool(result.get("isError", False))
