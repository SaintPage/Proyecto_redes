# Custom MCP Server & Chatbot Host

Project 1 — Ángel Mérida 23661.

A chatbot host that connects to several MCP (Model Context Protocol)
servers, including a custom one built for an industry use case. The MCP
protocol is implemented **manually over JSON-RPC 2.0**: no FastMCP, no
MCP SDK, no third-party protocol library.

## Status

| # | Feature | Status |
|---|---------|--------|
| 1 | LLM connection through the API | Pending |
| 2 | Context within a session | Pending |
| 3 | Log of all MCP interactions | Pending |
| 4 | Official servers (Filesystem, Git) | Pending |
| 5 | Custom local MCP server (pharmacy) | Done |
| 6 | Same server deployed remotely | Pending |
| 7 | Wireshark analysis | Pending |

## Custom server: pharmacy chain

The local MCP server models a pharmacy chain and exposes five tools:

| Tool | Purpose |
|------|---------|
| `search_medications` | Search the catalog by name, ingredient or category |
| `check_inventory` | Availability and price per branch |
| `suggest_products_for_symptom` | OTC category hints, with medical referral on red-flag symptoms |
| `create_order` | Place an order (atomic stock validation, GTQ totals) |
| `get_order_status` | Look up a persisted order |

Full specification (parameters, return shapes, examples) in
[`docs/server-spec.md`](docs/server-spec.md). Conclusions and notes in
[`docs/conclusions.md`](docs/conclusions.md).

## Architecture

```
server/
├── jsonrpc.py     JSON-RPC 2.0 message format (no MCP knowledge)
├── transport.py   stdio transport, newline-delimited JSON
├── mcp_server.py  MCP core: initialize, tools/list, tools/call
├── logger.py      diagnostics to stderr and logs/server.log
├── main.py        entry point wiring transport + core
└── tools/
    ├── registry.py           @tool decorator, schema validation
    ├── data_store.py         JSON loading + order persistence
    ├── pharmacy.py           search_medications, check_inventory
    ├── pharmacy_symptoms.py  suggest_products_for_symptom
    └── pharmacy_orders.py    create_order, get_order_status
```

The three layers are deliberately independent. `mcp_server.py` receives a
decoded message and returns the message to send back, so replacing the
stdio transport with HTTP (feature 6) does not require touching the
protocol logic.

## Requirements

- Python 3.10 or newer (no external dependencies for the server)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/SaintPage/Proyecto_redes.git
   cd Proyecto_redes
   ```
2. No third-party packages are required. Any Python 3.10+ interpreter
   will run the server as is.

## Running the server

The server speaks JSON-RPC over stdin/stdout, so it is normally launched
by a client. To try it by hand:

```bash
python -m server.main
```

Then paste one message per line:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0.1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_medications","arguments":{"query":"ibuprofeno"}}}
```

## Running the tests

```bash
python tests/test_handshake.py        # protocol lifecycle + error codes
python tests/test_pharmacy_tools.py   # search and inventory tools
python tests/test_pharmacy_orders.py  # symptom, order and status tools
```

`test_handshake.py` launches the server as a subprocess and verifies the
full lifecycle plus the JSON-RPC error codes (-32700, -32601, -32602).
The other two exercise the domain tools directly.

## Protocol notes

- Notifications (messages without `id`) are never answered.
- `stdout` carries protocol frames only; all logging goes to `stderr`.
- Tool execution failures are returned inside the result with
  `isError: true`, not as JSON-RPC errors. Protocol-level problems
  (unknown tool, invalid arguments) do use JSON-RPC error codes.


