"""
Cliente MCP sobre HTTP, implementado a mano.

Es la contraparte de mcp_client.py (stdio): en vez de lanzar un
subproceso y escribirle por su stdin, envia los mismos mensajes
JSON-RPC por POST a un endpoint remoto.

Expone exactamente la misma interfaz que MCPClient (start, stop,
call_tool, tools), de modo que el anfitrion puede usar un servidor
local o uno remoto sin cambiar una linea de su logica. Eso es lo que
pide el enunciado: "el chatbot debe hacer uso del servidor MCP remoto
tal y como utiliza el servidor local".

Usa urllib de la libreria estandar; no hace falta requests.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Optional

from .mcp_client import MCPClientError
from .mcp_log import MCPLog

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "pharmacy-chatbot", "version": "0.1.0"}
SESSION_HEADER = "Mcp-Session-Id"
TIMEOUT = 30  # segundos


class MCPHTTPClient:
    """Mantiene la conexion con UN servidor MCP remoto."""

    def __init__(self, name: str, url: str, log: MCPLog) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.log = log
        self.tools: list[dict] = []
        self.session_id: Optional[str] = None
        self._next_id = 1

    # -- ciclo de vida ---------------------------------------------------

    def start(self) -> dict:
        """Completa el handshake contra el servidor remoto."""
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })

        self._notify("notifications/initialized")

        tools_result = self._request("tools/list")
        self.tools = tools_result.get("tools", [])

        return result

    def stop(self) -> None:
        """Cierra la sesion en el servidor, si quedo abierta."""
        if not self.session_id:
            return
        request = urllib.request.Request(
            f"{self.url}/mcp", method="DELETE",
            headers={SESSION_HEADER: self.session_id},
        )
        try:
            urllib.request.urlopen(request, timeout=TIMEOUT).close()
        except (urllib.error.URLError, OSError):
            # Cerrar la sesion es cortesia: si el servidor no responde,
            # la sesion caduca sola del lado remoto.
            pass
        self.session_id = None

    # -- envio de mensajes -----------------------------------------------

    def _post(self, message: dict) -> tuple[int, Optional[dict], dict]:
        """
        Envia un mensaje por POST y retorna (status, cuerpo, encabezados).

        El cuerpo es None cuando la respuesta no trae contenido, que es
        lo que ocurre con las notificaciones (202 Accepted).
        """
        data = json.dumps(message, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.session_id:
            headers[SESSION_HEADER] = self.session_id

        request = urllib.request.Request(
            f"{self.url}/mcp", data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
                status = response.status
                response_headers = dict(response.headers)
        except urllib.error.HTTPError as exc:
            # Un 4xx/5xx puede traer igual un error JSON-RPC util.
            raw = exc.read()
            status = exc.code
            response_headers = dict(exc.headers or {})
        except (urllib.error.URLError, OSError) as exc:
            raise MCPClientError(
                f"No se pudo contactar '{self.name}' en {self.url}: {exc}"
            ) from exc

        if not raw:
            return status, None, response_headers

        try:
            return status, json.loads(raw.decode("utf-8")), response_headers
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MCPClientError(
                f"Respuesta invalida de '{self.name}': {exc}"
            ) from exc

    def _request(self, method: str, params: Optional[dict] = None) -> dict:
        """Envia una solicitud y espera su respuesta."""
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._next_id += 1

        self.log.request(self.name, message)
        status, response, headers = self._post(message)

        # El servidor asigna el id de sesion al responder initialize.
        new_session = headers.get(SESSION_HEADER)
        if new_session:
            self.session_id = new_session

        if response is None:
            raise MCPClientError(
                f"{self.name}: el servidor respondio {status} sin cuerpo"
            )

        self.log.response(self.name, response)

        if "error" in response:
            error = response["error"]
            raise MCPClientError(
                f"{self.name}: error {error.get('code')} - {error.get('message')}"
            )
        return response.get("result", {})

    def _notify(self, method: str, params: Optional[dict] = None) -> None:
        """Envia una notificacion. No espera respuesta (202 Accepted)."""
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params

        self.log.notification(self.name, message)
        self._post(message)

    # -- uso de herramientas ---------------------------------------------

    def call_tool(self, tool_name: str, arguments: dict) -> tuple[str, bool]:
        """
        Ejecuta una tool en el servidor remoto.

        Misma firma y mismo comportamiento que en el cliente stdio.
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
