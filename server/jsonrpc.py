"""
Pure JSON-RPC 2.0 layer.

This module knows NOTHING about MCP. It only deals with the message
format defined by the JSON-RPC 2.0 specification (https://www.jsonrpc.org/).

Keeping this separate from the MCP logic means the protocol layer can be
unit-tested on its own, and the same code can later be reused over a
different transport (stdio now, HTTP later).
"""

from typing import Any, Optional

JSONRPC_VERSION = "2.0"

# --- Standard JSON-RPC 2.0 error codes ---------------------------------
PARSE_ERROR = -32700       # Invalid JSON was received
INVALID_REQUEST = -32600   # The JSON sent is not a valid Request object
METHOD_NOT_FOUND = -32601  # The method does not exist / is not available
INVALID_PARAMS = -32602    # Invalid method parameter(s)
INTERNAL_ERROR = -32603    # Internal JSON-RPC error


def make_response(request_id: Any, result: Any) -> dict:
    """Build a successful JSON-RPC response object."""
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def make_error(
    request_id: Any,
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> dict:
    """Build a JSON-RPC error response object."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def is_notification(message: dict) -> bool:
    """
    A notification is a Request object without an "id" member.

    Per the specification, the server MUST NOT reply to a notification.
    """
    return "id" not in message


def validate_request(message: Any) -> Optional[str]:
    """
    Check that `message` is a structurally valid JSON-RPC 2.0 Request.

    Returns None if valid, or a human-readable reason if it is not.
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
