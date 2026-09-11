# Remote MCP Server — Deployment Guide

Report section 8 (remote server). This document covers how the pharmacy
MCP server runs remotely over HTTP, and how to deploy it.

The remote server exposes **the same five tools** as the local one. The
protocol core (`server/mcp_server.py`) and the tools are unchanged; only
the transport differs.

---

## 1. Local vs remote: what actually changes

| | Local | Remote |
|---|---|---|
| Transport | stdio (stdin/stdout) | HTTP (Streamable HTTP) |
| Module | `server/main.py` | `server/main_http.py` |
| Transport code | `server/transport.py` | `server/http_transport.py` |
| Client | `chatbot/mcp_client.py` | `chatbot/mcp_http_client.py` |
| Protocol core | `server/mcp_server.py` | **the same file** |
| Tools | `server/tools/` | **the same files** |

This is the payoff of the layered design: going remote required writing
a new transport, not rewriting the server.

## 2. HTTP endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/mcp` | Carries every JSON-RPC message. |
| `GET` | `/health` | Health check for the cloud platform. |
| `GET` | `/` | Same as `/health`. |
| `DELETE` | `/mcp` | Closes the session (`Mcp-Session-Id` header). |

### POST /mcp

Request body is a single JSON-RPC message. Responses:

| Situation | Status | Body |
|---|---|---|
| Request (has `id`) | `200` | JSON-RPC response |
| Notification (no `id`) | `202` | empty — the spec forbids answering |
| Malformed JSON | `400` | JSON-RPC error `-32700` |
| Missing/oversized body | `400` | JSON-RPC error `-32600` |
| Unknown path | `404` | `{"error": "Not found"}` |

### Session handling

stdio gave one process per client, so sessions were implicit. Over HTTP
a single endpoint serves many clients, so the server assigns a session:

1. Client sends `initialize`.
2. Server replies with an `Mcp-Session-Id` header.
3. Client echoes that header on every later request.
4. Client may `DELETE /mcp` to close it.

Requests without a valid session are still served with an ephemeral
server instance, so the endpoint stays usable from `curl`.

## 3. Running it locally

```bash
python -m server.main_http            # port 8080, or $PORT
python -m server.main_http --port 9000
```

Check it:

```bash
curl http://127.0.0.1:8080/health
```

Full handshake by hand:

```bash
curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'

curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

## 4. Pointing the chatbot at it

Set `MCP_REMOTE_URL` to the server root (no `/mcp` suffix):

```powershell
$env:MCP_REMOTE_URL="http://127.0.0.1:8080"      # local test
$env:MCP_REMOTE_URL="https://your-service.run.app" # deployed
python -m chatbot.main
```

When that variable is set, the host connects to the remote pharmacy
server **instead of** the local stdio one — they are the same server, so
running both would duplicate every tool. The Filesystem and Git servers
keep running locally.

On startup the host prints which one it used:

```
OK pharmacy (remoto): 5 herramientas — https://your-service.run.app
```

## 5. Deploying

The repository includes a `Dockerfile`. The image carries only
`server/` and `data/` — the chatbot, tests and docs stay out.

### Google Cloud Run

```bash
gcloud run deploy pharmacy-mcp \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

Cloud Run injects `PORT`; the server reads it. The command prints the
public URL, which is what goes in `MCP_REMOTE_URL`.

Note: Cloud Run has a free tier but requires a billing account on the
project.

### Other container platforms

Any platform that runs a Dockerfile works the same way — Render,
Fly.io, Railway. They all inject `PORT` and expect the process to listen
on `0.0.0.0`, which this server already does.

### Verifying a deployment

```bash
curl https://your-service.example.com/health
```

A JSON body with `"status": "ok"` means the server is up.

## 6. Note on capturing traffic (report section 7)

Cloud platforms serve over HTTPS, so a Wireshark capture against a
deployed URL shows encrypted TLS records rather than JSON-RPC messages.
Two ways around it:

- Run the same HTTP server on a machine reachable over the network (or
  on localhost) without TLS, and capture there. The JSON-RPC messages
  are then visible in plain text.
- Capture against the HTTPS deployment and decrypt in Wireshark using
  an `SSLKEYLOGFILE`.

Either way the messages are the same, because the transport is the same
code.
