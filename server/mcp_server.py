"""
Nucleo del protocolo MCP.

Implementa el lado servidor del Model Context Protocol a mano sobre
JSON-RPC 2.0, sin FastMCP ni ningun SDK de MCP, tal como lo exige el
enunciado del proyecto.

Ciclo de vida manejado aqui:

    cliente -> initialize                  (request)
    servidor -> InitializeResult           (response)
    cliente -> notifications/initialized   (notification, sin respuesta)
    cliente -> tools/list                  (request)
    cliente -> tools/call                  (request)

Esta clase es independiente del transporte: recibe un mensaje ya
decodificado y retorna el mensaje que se debe enviar de vuelta (o None
para las notificaciones).
"""

from typing import Any, Optional

from . import jsonrpc
from .logger import get_logger
from .tools import registry

# Revision de protocolo que implementa este servidor. Si el cliente pide
# una version que conocemos, se la devolvemos tal cual; si no, respondemos
# con la nuestra y dejamos que el cliente decida si puede continuar.
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}

SERVER_INFO = {"name": "custom-mcp-server", "version": "0.1.0"}

log = get_logger()


class MCPServer:
    """Despacha metodos de MCP y produce respuestas de JSON-RPC."""

    def __init__(self) -> None:
        self.initialized = False
        self._handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "ping": self._handle_ping,
        }

    # -- punto de entrada -------------------------------------------------

    def handle_message(self, message: Any) -> Optional[dict]:
        """
        Procesa un mensaje entrante.

        Retorna el objeto de respuesta, o None cuando no hay que enviar
        nada de vuelta (notificaciones).
        """
        reason = jsonrpc.validate_request(message)
        if reason:
            log.warning("Invalid request: %s", reason)
            request_id = message.get("id") if isinstance(message, dict) else None
            return jsonrpc.make_error(
                request_id, jsonrpc.INVALID_REQUEST, "Invalid Request", reason
            )

        method = message["method"]
        params = message.get("params", {}) or {}

        if jsonrpc.is_notification(message):
            log.info("<- notification: %s", method)
            self._handle_notification(method, params)
            return None

        request_id = message["id"]
        log.info("<- request #%s: %s", request_id, method)

        handler = self._handlers.get(method)
        if handler is None:
            return jsonrpc.make_error(
                request_id,
                jsonrpc.METHOD_NOT_FOUND,
                f"Method not found: {method}",
            )

        try:
            return handler(request_id, params)
        except Exception as exc:  # nunca dejar morir al servidor por un mensaje
            log.exception("Unhandled error in %s", method)
            return jsonrpc.make_error(
                request_id, jsonrpc.INTERNAL_ERROR, "Internal error", str(exc)
            )

    # -- notificaciones -----------------------------------------------------

    def _handle_notification(self, method: str, params: dict) -> None:
        if method == "notifications/initialized":
            # El cliente confirma que el handshake esta completo.
            self.initialized = True
            log.info("Handshake complete, server ready")
        # Las notificaciones desconocidas se ignoran a proposito: la
        # especificacion prohibe responderlas, incluso con un error.

    # -- manejadores de requests ---------------------------------------------

    def _handle_initialize(self, request_id: Any, params: dict) -> dict:
        requested = params.get("protocolVersion")
        negotiated = requested if requested in SUPPORTED_VERSIONS else PROTOCOL_VERSION
        client = params.get("clientInfo", {})
        log.info("Client: %s, protocol: %s", client.get("name", "?"), negotiated)

        return jsonrpc.make_response(
            request_id,
            {
                "protocolVersion": negotiated,
                # Declarar la capacidad "tools" le indica al cliente que
                # puede llamar a tools/list. Objeto vacio = sin
                # sub-caracteristicas opcionales.
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )

    def _handle_ping(self, request_id: Any, params: dict) -> dict:
        return jsonrpc.make_response(request_id, {})

    def _handle_tools_list(self, request_id: Any, params: dict) -> dict:
        tools = registry.list_tools()
        log.info("-> tools/list: %d tool(s)", len(tools))
        return jsonrpc.make_response(request_id, {"tools": tools})

    def _handle_tools_call(self, request_id: Any, params: dict) -> dict:
        name = params.get("name")
        arguments = params.get("arguments", {}) or {}

        if not isinstance(name, str):
            return jsonrpc.make_error(
                request_id, jsonrpc.INVALID_PARAMS, 'Missing "name" parameter'
            )

        entry = registry.get_tool(name)
        if entry is None:
            return jsonrpc.make_error(
                request_id, jsonrpc.INVALID_PARAMS, f"Unknown tool: {name}"
            )

        reason = registry.validate_arguments(entry["inputSchema"], arguments)
        if reason:
            return jsonrpc.make_error(
                request_id, jsonrpc.INVALID_PARAMS, "Invalid arguments", reason
            )

        try:
            result = entry["handler"](**arguments)
        except Exception as exc:
            # Los fallos de ejecucion de la tool NO son errores de
            # protocolo: se retornan dentro del resultado con
            # isError=true para que el LLM pueda leer el mensaje y
            # reaccionar (reintentar, preguntar al usuario, etc.).
            log.error("Tool '%s' failed: %s", name, exc)
            return jsonrpc.make_response(
                request_id,
                {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                },
            )

        log.info("-> tools/call '%s' ok", name)
        return jsonrpc.make_response(
            request_id,
            {
                "content": [{"type": "text", "text": str(result)}],
                "isError": False,
            },
        )