"""
Entry point: wires the stdio transport to the MCP protocol core.

Run it directly for manual testing:

    python -m server.main

then paste a JSON-RPC message and press Enter.
"""

from . import jsonrpc
from .logger import get_logger
from .mcp_server import MCPServer
from .transport import StdioTransport

log = get_logger()


def main() -> None:
    transport = StdioTransport()
    server = MCPServer()
    log.info("MCP server started (stdio transport)")

    for message, parse_error in transport.receive():
        if parse_error is not None:
            transport.send(
                jsonrpc.make_error(None, jsonrpc.PARSE_ERROR, "Parse error", parse_error)
            )
            continue

        response = server.handle_message(message)
        if response is not None:
            transport.send(response)

    log.info("stdin closed, shutting down")


if __name__ == "__main__":
    main()
