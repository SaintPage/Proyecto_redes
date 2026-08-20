"""
MCP protocol core.

Implements the server side of the Model Context Protocol manually on top
of JSON-RPC 2.0, without FastMCP or any MCP SDK, as required by the
project statement.

Lifecycle handled here:

    client -> initialize                  (request)
    server -> InitializeResult            (response)
    client -> notifications/initialized   (notification, no reply)
    client -> tools/list                  (request)
    client -> tools/call                  (request)

This class is transport-agnostic: it takes a decoded message and returns
the message to send back (or None for notifications).
"""

from typing import Any, Optional

from . import jsonrpc
from .logger import get_logger
from .tools import registry

# Protocol revision this server implements. If the client asks for a
# version we know, we echo it back; otherwise we answer with ours and let
# the client decide whether it can continue.
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}

SERVER_INFO = {"name": "custom-mcp-server", "version": "0.1.0"}

log = get_logger()


class MCPServer:
    """Dispatches MCP methods and produces JSON-RPC responses."""

    def __init__(self) -> None:
        self.initialized = False
        self._handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "ping": self._handle_ping,
        }

    # -- entry point ----------------------------------------------------

    def handle_message(self, message: Any) -> Optional[dict]:
        """
        Process one incoming message.

        Returns the response object, or None when nothing must be sent
        back (notifications).
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
        except Exception as exc:  # never let the server die on one message
            log.exception("Unhandled error in %s", method)
            return jsonrpc.make_error(
                request_id, jsonrpc.INTERNAL_ERROR, "Internal error", str(exc)
            )

    # -- notifications --------------------------------------------------

    def _handle_notification(self, method: str, params: dict) -> None:
        if method == "notifications/initialized":
            # The client confirms the handshake is complete.
            self.initialized = True
            log.info("Handshake complete, server ready")
        # Unknown notifications are ignored on purpose: the spec forbids
        # answering them, even with an error.

    # -- request handlers -----------------------------------------------

    def _handle_initialize(self, request_id: Any, params: dict) -> dict:
        requested = params.get("protocolVersion")
        negotiated = requested if requested in SUPPORTED_VERSIONS else PROTOCOL_VERSION
        client = params.get("clientInfo", {})
        log.info("Client: %s, protocol: %s", client.get("name", "?"), negotiated)

        return jsonrpc.make_response(
            request_id,
            {
                "protocolVersion": negotiated,
                # Declaring the "tools" capability tells the client it can
                # call tools/list. Empty object = no optional sub-features.
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
            # Tool execution failures are NOT protocol errors: they are
            # returned inside the result with isError=true so the LLM can
            # read the message and react (retry, ask the user, etc.).
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
