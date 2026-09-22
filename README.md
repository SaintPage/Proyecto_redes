# Custom MCP Server & Chatbot Host

Project 1 — Ángel Mérida 23661.

CC3067 Networks, Universidad del Valle de Guatemala.

A chatbot host that connects to several MCP (Model Context Protocol)
servers, including a custom one built for an industry use case. The MCP
protocol is implemented **manually over JSON-RPC 2.0**: no FastMCP, no
MCP SDK, no third-party protocol library. Both sides are hand-written —
the server that exposes the tools and the client the host uses to reach
every server, including the official ones.

## Status

| # | Feature | Status |
|---|---------|--------|
| 1 | LLM connection through its API (Gemini) | Done |
| 2 | Context kept within a session | Done |
| 3 | Log of every interaction with MCP servers | Done |
| 4 | Official Filesystem and Git MCP servers | Done |
| 5 | Custom local MCP server (pharmacy chain) | Done |
| 6 | Same server deployed remotely (AWS ECS) | Done |
| 7 | Wireshark capture and analysis | Done |

## How it fits together

```
                    ┌──────────────── chatbot host ────────────────┐
                    │  Gemini API  ·  session context  ·  MCP log  │
                    └──────┬──────────────┬──────────────┬─────────┘
                           │              │              │
                  MCP client        MCP client      MCP client
                  (stdio or HTTP)   (stdio)         (stdio)
                           │              │              │
              ┌────────────┴──┐   ┌───────┴──────┐  ┌────┴────────┐
              │ pharmacy      │   │ filesystem   │  │ git         │
              │ (custom)      │   │ (official)   │  │ (official)  │
              │ local or AWS  │   │ Node.js      │  │ Python      │
              └───────────────┘   └──────────────┘  └─────────────┘
```

The host starts one MCP client per server, gathers all their tools, and
hands them to the LLM. When the model asks for a tool, the host routes
the call to the right server and returns the result to the model. Tool
names are prefixed with the server name (`pharmacy__check_inventory`,
`git__git_commit`) so the routing is unambiguous.

## Requirements

- **Python 3.10 or newer**
- **Node.js 18 or newer** — runs the official Filesystem server via `npx`
- **Git** — used by the official Git server
- **A Gemini API key** — free at <https://aistudio.google.com/apikey>,
  no credit card needed. Do not enable billing on that Google project,
  or the free tier is lost.

Only for deploying or analyzing (not needed to run the chatbot):
Docker, the AWS CLI and Wireshark.

## Installation

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/SaintPage/Proyecto_redes.git
   cd Proyecto_redes
   ```

2. Install the Python dependencies (the Gemini client and the official
   Git server):

   ```bash
   pip install -r requirements.txt
   ```

3. Check that Node.js and Git are available:

   ```bash
   node --version
   git --version
   ```

   On Windows, if a tool was installed while the terminal was open,
   close and reopen the terminal so it picks up the new `PATH`.

4. Set the API key for the current terminal session:

   ```powershell
   # PowerShell
   $env:GEMINI_API_KEY="your-key"
   ```

   ```bash
   # Git Bash / Linux / macOS
   export GEMINI_API_KEY="your-key"
   ```

   Never write the key into a file of this repository.

5. Verify everything without spending API quota:

   ```bash
   python tests/test_mcp_client.py
   python tests/test_official_servers.py
   ```

## Usage

### Start the chatbot

```bash
python -m chatbot.main
```

On startup the host prepares the `demo/` workspace, connects the three
MCP servers and prints the handshake of each one:

```
Conectando servidores MCP...
[MCP →] pharmacy #1 initialize
[MCP ←] pharmacy #1 ok
[MCP →] pharmacy (notificacion) notifications/initialized
[MCP →] pharmacy #2 tools/list
[MCP ←] pharmacy #2 ok
  OK pharmacy: 5 herramientas
  OK filesystem: 14 herramientas
  OK git: 12 herramientas
  OK LLM: gemini-3.6-flash
```

### Commands inside the chat

- `/tools` — list every tool the model can use
- `/log` — show the full log of MCP requests and responses
- `/reset` — clear the conversation context
- `/salir` — end the session (also `/quit`, `/exit`)

Run with `--debug` to print full tracebacks on errors.

### Demonstration prompts

| Feature | Prompt |
|---|---|
| 1. General knowledge | `¿Quién fue Alan Turing?` |
| 2. Session context | then: `¿En qué fecha nació?` |
| 5. Custom server | `¿tienen ibuprofeno disponible en Mixco?` |
| 5. Safety rule | `me duele el pecho` — refers to medical care, suggests no product |
| 4. Official servers | `crea un archivo README.md que diga "Proyecto Demo", agrégalo al repositorio y haz un commit` |
| 3. Interaction log | `/log` |

The Filesystem and Git servers can only touch the `demo/` folder. Any
write outside it is rejected by the Filesystem server itself.

### Using the remote server

Point the host at the deployed server (the root URL, without `/mcp`):

```powershell
$env:MCP_REMOTE_URL="https://<your-service>.ecs.us-east-2.on.aws"
python -m chatbot.main
```

The host then reaches the pharmacy server over HTTPS **instead of** the
local process, while Filesystem and Git keep running locally. On startup
it prints `OK pharmacy (remoto): 5 herramientas — <url>`.

To try the HTTP transport without deploying, start it locally in a
second terminal and use `http://127.0.0.1:8080` as the URL:

```bash
python -m server.main_http
```

### Environment variables

- `GEMINI_API_KEY` — required. API key for the LLM.
- `GEMINI_MODEL` — optional. Defaults to `gemini-3.6-flash`. Run
  `python scripts/list_models.py` to see the models your key can use.
- `MCP_REMOTE_URL` — optional. Use the remote pharmacy server.
- `SSLKEYLOGFILE` — only for the Wireshark analysis. Makes Python write
  its TLS session keys so the capture can be decrypted. Unset it when
  done.

## The custom server: a pharmacy chain

| Tool | Purpose |
|------|---------|
| `search_medications` | Search the catalog by name, active ingredient or category |
| `check_inventory` | Availability and price per branch |
| `suggest_products_for_symptom` | Over-the-counter category hints; refers red-flag symptoms to medical care |
| `create_order` | Place an order, validating every item before touching stock |
| `get_order_status` | Look up a stored order |

All data is fictional (18 products, 3 branches in Guatemala, prices in
GTQ). Parameters, return shapes and examples are in
[`docs/server-spec.md`](docs/server-spec.md).

The server runs over two transports that share the same protocol core
and tools:

```bash
python -m server.main        # stdio — launched by the host
python -m server.main_http   # HTTP — for remote deployment
```

## Remote deployment

The server is deployed on **AWS ECS Express Mode** from the included
`Dockerfile`. The image contains only `server/` and `data/`.

```bash
aws ecr create-repository --repository-name pharmacy-mcp --region us-east-2
aws ecr get-login-password --region us-east-2 | docker login --username AWS \
    --password-stdin <account-id>.dkr.ecr.us-east-2.amazonaws.com
docker build -t pharmacy-mcp .
docker tag pharmacy-mcp:latest <account-id>.dkr.ecr.us-east-2.amazonaws.com/pharmacy-mcp:latest
docker push <account-id>.dkr.ecr.us-east-2.amazonaws.com/pharmacy-mcp:latest
```

Then, in the ECS console → Express mode, create a service from that
image with container port `8080`, health check path `/health`, and
0.25 vCPU / 0.5 GB. Full steps, endpoints and caveats are in
[`docs/remote-server.md`](docs/remote-server.md).

Check a deployment with:

```bash
curl https://<your-service>.ecs.us-east-2.on.aws/health
```

## Project structure

```
server/                  custom MCP server
├── jsonrpc.py           JSON-RPC 2.0 message format (knows nothing of MCP)
├── mcp_server.py        MCP core: initialize, tools/list, tools/call
├── transport.py         stdio transport, newline-delimited JSON
├── http_transport.py    HTTP transport (Streamable HTTP) with sessions
├── main.py / main_http.py   entry points for each transport
├── logger.py            diagnostics to stderr and logs/, never stdout
└── tools/               the five pharmacy tools and their registry
chatbot/                 host
├── main.py              chat loop and tool-use loop
├── llm_client.py        Gemini API, retries on 429/500/503
├── conversation.py      session context
├── mcp_client.py        MCP client over stdio
├── mcp_http_client.py   MCP client over HTTP, same interface
├── mcp_log.py           log of every MCP interaction
└── servers_config.py    which servers to start, demo/ workspace
data/                    fictional catalog, inventory and symptom map
tests/                   six test suites
docs/                    specification, analysis, conclusions, slides
scripts/list_models.py   lists the Gemini models your key can use
Dockerfile               image for the remote server
```

## Tests

None of them needs an API key.

```bash
python tests/test_handshake.py         # MCP lifecycle and JSON-RPC error codes
python tests/test_pharmacy_tools.py    # search and inventory
python tests/test_pharmacy_orders.py   # symptoms, orders and order status
python tests/test_mcp_client.py        # host's MCP client against the server
python tests/test_http_server.py       # remote transport over HTTP
python tests/test_official_servers.py  # Filesystem and Git scenario (needs Node.js)
```

80 checks in total.

## Documentation

- [`docs/server-spec.md`](docs/server-spec.md) — server specification:
  transport, methods, tools, parameters, examples (report section 8)
- [`docs/remote-server.md`](docs/remote-server.md) — remote server:
  HTTP endpoints, sessions and deployment (report section 8)
- [`docs/wireshark-analysis.md`](docs/wireshark-analysis.md) — capture,
  message classification and layer analysis (report sections 7 and 9);
  also as [`.docx`](docs/analisis-wireshark.docx)
- [`docs/conclusions.md`](docs/conclusions.md) — conclusions and
  comments (report section 10)
- `docs/evidencia/` — screenshots and the decrypted capture

## Protocol notes

- Notifications (messages without `id`) are never answered. Over HTTP
  that means `202 Accepted` with an empty body.
- `stdout` carries protocol frames only; all logging goes to `stderr`.
- Tool execution failures come back inside the result with
  `isError: true`. Protocol problems (unknown tool, invalid arguments)
  use JSON-RPC error codes (`-32700`, `-32601`, `-32602`).
- Over HTTP the server assigns an `Mcp-Session-Id` on `initialize`; the
  client echoes it on every request and closes it with `DELETE /mcp`.

## Troubleshooting

- **`node` or `gcloud`/`aws` not recognized after installing** — close
  and reopen the terminal.
- **PowerShell refuses to run a script** — run
  `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
- **`404 ... model is no longer available`** — the key cannot use that
  model; set `GEMINI_MODEL` to one from `scripts/list_models.py`.
- **`429` or `503` from the API** — the free tier is rate-limited. The
  host retries automatically, waiting as long as the API asks. If it
  still fails, wait a minute between prompts.
- **Filesystem server fails on Windows** — make sure Node.js is
  installed; the host already launches `npx` through `cmd /c`.

## Third-party components

- Official MCP servers by Anthropic: Filesystem
  (`@modelcontextprotocol/server-filesystem`) and Git (`mcp-server-git`).
  They run as separate processes; this project talks to them through
  its own hand-written client.
- Google Gen AI SDK (`google-genai`) as the LLM API client.

## License

Academic project.
