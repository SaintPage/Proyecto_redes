"""
Capa pura de JSON-RPC 2.0.

Este modulo NO sabe nada de MCP. Solo se encarga del formato de mensajes
definido por la especificacion de JSON-RPC 2.0 (https://www.jsonrpc.org/).

Mantener esto separado de la logica de MCP permite probar la capa de
protocolo de forma aislada, y reutilizar el mismo codigo con un
transporte distinto mas adelante (stdio ahora, HTTP despues).
"""

from typing import Any, Optional

JSONRPC_VERSION = "2.0"

# --- Codigos de error estandar de JSON-RPC 2.0 --------------------------
PARSE_ERROR = -32700       # Se recibio un JSON invalido
INVALID_REQUEST = -32600   # El JSON enviado no es un objeto Request valido
METHOD_NOT_FOUND = -32601  # El metodo no existe o no esta disponible
INVALID_PARAMS = -32602    # Parametro(s) invalido(s) del metodo
INTERNAL_ERROR = -32603    # Error interno de JSON-RPC


def make_response(request_id: Any, result: Any) -> dict:
    """Construye un objeto de respuesta exitosa de JSON-RPC."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def make_error(
    request_id: Any,
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> dict:
    """Construye un objeto de respuesta de error de JSON-RPC."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def is_notification(message: dict) -> bool:
    """
    Una notificacion es un objeto Request sin el miembro "id".

    Segun la especificacion, el servidor NO DEBE responder a una
    notificacion.
    """
    return "id" not in message


def validate_request(message: Any) -> Optional[str]:
    """
    Verifica que `message` sea un Request de JSON-RPC 2.0 estructuralmente
    valido.

    Retorna None si es valido, o una razon legible si no lo es.
    """
    if not isinstance(message, dict):
        return "Request must be a JSON object"
    if message.get("jsonrpc") != JSONRPC_VERSION:
        return f'Missing or invalid "jsonrpc" member (expected "{JSONRPC_VERSION}")'
    method = message.get("method")
    if not isinstance(method, str) or not method:
        return 'Missing or invalid "method" member'
    if "params" in message and not isinstance(message["params"], (dict, list)):
        return '"params" must be an object or an array'
    return None