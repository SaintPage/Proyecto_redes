"""
Transporte HTTP para MCP (funcionalidad 6).

Implementa el transporte "Streamable HTTP" del protocolo MCP a mano,
sobre la libreria estandar de Python. No se usa ningun framework web
ni SDK de MCP.

Como funciona:

    POST /mcp   -> recibe un mensaje JSON-RPC en el cuerpo y responde
                   con el mensaje de respuesta (application/json).
                   Si el mensaje es una notificacion, responde
                   202 Accepted sin cuerpo, porque el protocolo
                   prohibe responder a las notificaciones.
    GET  /health -> verificacion de estado, para la plataforma de nube.

El punto clave del diseno en capas: este modulo reemplaza a
transport.py (stdio), pero mcp_server.py NO cambia en absoluto. El
nucleo del protocolo recibe un mensaje decodificado y devuelve el
mensaje de respuesta, sin saber si viajo por una tuberia o por la red.

Gestion de sesion:
El protocolo permite que el servidor asigne un identificador de sesion
en la respuesta a initialize, mediante el encabezado Mcp-Session-Id.
El cliente lo reenvia en las siguientes peticiones. Eso permite
distinguir conversaciones distintas sobre el mismo endpoint, algo que
en stdio era implicito (un proceso por cliente).
"""

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from . import jsonrpc
from .logger import get_logger
from .mcp_server import MCPServer

log = get_logger("mcp-http")

MCP_PATH = "/mcp"
SESSION_HEADER = "Mcp-Session-Id"

# Tamano maximo de cuerpo aceptado, para no agotar memoria con una
# peticion malintencionada.
MAX_BODY_BYTES = 1_000_000

# Sesiones activas: id -> instancia de MCPServer. Cada sesion mantiene
# su propio estado de handshake.
_sessions: dict[str, MCPServer] = {}


class MCPHTTPHandler(BaseHTTPRequestHandler):
    """Atiende las peticiones HTTP del endpoint MCP."""

    # Identificacion del servidor en el encabezado Server.
    server_version = "custom-mcp-server/0.1.0"
    sys_version = ""

    #  utilidades de respuesta 

    def _send_json(self, payload: dict, status: int = 200,
                   session_id: Optional[str] = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if session_id:
            self.send_header(SESSION_HEADER, session_id)
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Redirige el log de acceso al logger del proyecto."""
        log.info("%s - %s", self.address_string(), format % args)

    #  manejadores 

    def do_GET(self) -> None:
        if self.path in ("/health", "/"):
            self._send_json({
                "status": "ok",
                "server": "custom-mcp-server",
                "transport": "streamable-http",
                "endpoint": MCP_PATH,
                "sessions": len(_sessions),
            })
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != MCP_PATH:
            self._send_json({"error": "Not found"}, status=404)
            return

        #  leer el cuerpo 
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0

        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(
                jsonrpc.make_error(None, jsonrpc.INVALID_REQUEST,
                                   "Invalid Request",
                                   "Missing or oversized body"),
                status=400,
            )
            return

        raw = self.rfile.read(length)

        try:
            message = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json(
                jsonrpc.make_error(None, jsonrpc.PARSE_ERROR,
                                   "Parse error", str(exc)),
                status=400,
            )
            return

        #  resolver la sesion 
        session_id = self.headers.get(SESSION_HEADER)
        is_initialize = (
            isinstance(message, dict) and message.get("method") == "initialize"
        )

        if is_initialize:
            # Una peticion initialize siempre abre una sesion nueva.
            session_id = uuid.uuid4().hex
            _sessions[session_id] = MCPServer()
            log.info("Nueva sesion: %s", session_id)
        elif session_id and session_id in _sessions:
            pass  # sesion conocida
        else:
            # Sin sesion valida se atiende igual, con un servidor
            # efimero: asi el endpoint sigue siendo utilizable con
            # herramientas simples como curl.
            session_id = None

        mcp = _sessions.get(session_id) if session_id else MCPServer()

        #  despachar al nucleo del protocolo 
        response = mcp.handle_message(message)

        if response is None:
            # Era una notificacion: no lleva cuerpo de respuesta.
            self._send_empty(202)
            return

        self._send_json(
            response,
            status=200,
            session_id=session_id if is_initialize else None,
        )

    def do_DELETE(self) -> None:
        """Permite al cliente cerrar explicitamente su sesion."""
        session_id = self.headers.get(SESSION_HEADER)
        if session_id and session_id in _sessions:
            del _sessions[session_id]
            log.info("Sesion cerrada: %s", session_id)
            self._send_empty(204)
            return
        self._send_empty(404)


def serve(host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    """
    Arranca el servidor HTTP.

    El puerto se toma de la variable de entorno PORT cuando existe,
    que es la convencion de las plataformas de nube (Cloud Run, Render,
    etc.). Localmente cae en 8080.
    """
    if port is None:
        port = int(os.environ.get("PORT", "8080"))

    httpd = ThreadingHTTPServer((host, port), MCPHTTPHandler)
    log.info("Servidor MCP HTTP escuchando en %s:%d%s", host, port, MCP_PATH)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Interrumpido, cerrando")
    finally:
        httpd.server_close()
