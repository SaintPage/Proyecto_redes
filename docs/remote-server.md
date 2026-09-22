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

## 5. Deploying on AWS ECS Express Mode

The server runs on **Amazon ECS Express Mode**, which takes a container
image and provisions the rest: a Fargate task, an Application Load
Balancer with an HTTPS endpoint, health checks and auto scaling.

Two other platforms were tried first and ruled out:

- **Google Cloud Run** requires a one-time USD 30 prepayment for billing
  accounts created in Guatemala.
- **AWS App Runner** stopped accepting new customers on April 30, 2026.

### 5.1 Build and push the image

Express Mode deploys from a container registry, not from source code, so
the image is built locally and pushed to Amazon ECR:

```bash
# once: create the repository
aws ecr create-repository --repository-name pharmacy-mcp --region us-east-2

# authenticate Docker against ECR
aws ecr get-login-password --region us-east-2 | docker login --username AWS \
    --password-stdin <account-id>.dkr.ecr.us-east-2.amazonaws.com

# build, tag and push
docker build -t pharmacy-mcp .
docker tag pharmacy-mcp:latest <account-id>.dkr.ecr.us-east-2.amazonaws.com/pharmacy-mcp:latest
docker push <account-id>.dkr.ecr.us-east-2.amazonaws.com/pharmacy-mcp:latest
```

The image carries only `server/` and `data/`; `.dockerignore` keeps the
chatbot, tests and docs out. Before pushing, it can be tested locally:

```bash
docker run -p 8080:8080 pharmacy-mcp
curl http://localhost:8080/health
```

For the CLI, `aws login` gives temporary credentials from the console
session, which avoids creating long-lived access keys for the root user.

### 5.2 Create the service

In the ECS console → **Express mode**:

| Setting | Value |
|---|---|
| Image URI | `<account-id>.dkr.ecr.us-east-2.amazonaws.com/pharmacy-mcp:latest` |
| Task execution role / infrastructure role | create new (defaults) |
| Container port | `8080` |
| Health check path | `/health` |
| CPU / memory | 0.25 vCPU / 0.5 GB |
| Environment variables | none (`PORT=8080` is set in the image) |

When the deployment finishes, the service page shows the application
URL, for example `https://ph-<id>.ecs.us-east-2.on.aws`. That is the
value for `MCP_REMOTE_URL`.

### 5.3 Verifying

```bash
curl https://<your-service>.ecs.us-east-2.on.aws/health
```

A body with `"status": "ok"` means the load balancer is routing to a
healthy task.

### 5.4 Cost

Express Mode itself is free; the underlying resources are billed:
roughly USD 16/month for the load balancer and USD 2/month for the
smallest Fargate task. The load balancer is billed while the service
exists, even with no traffic, so **the service must be deleted after the
evaluation**. The image can stay in ECR and be redeployed in minutes.

## 6. Known limitations of the deployment

- **Orders are not durable.** Fargate tasks have an ephemeral
  filesystem. `create_order` writes to `data/orders.json` inside the
  container, so orders disappear when the task restarts, and two tasks
  would each keep their own orders. A real deployment would store them
  in an external database.
- **The endpoint is public.** The service accepts requests from anyone
  who knows the URL, including `create_order`. The data is fictional,
  but a real deployment would require an API key or token on every
  request.
- **One connection per message.** The host's HTTP client sends
  `Connection: close`, so every JSON-RPC message pays a full TCP and TLS
  handshake. The Wireshark analysis measures this at about 300 ms per
  message, of which about 100 ms is the actual request. Persistent
  connections would remove most of that overhead.

## 7. Capturing the traffic (report section 7)

The load balancer only serves HTTPS, so a capture against the deployed
URL shows TLS records instead of JSON-RPC messages. The capture in
[`wireshark-analysis.md`](wireshark-analysis.md) was decrypted by
setting `SSLKEYLOGFILE` before starting the host: Python writes each TLS
session's secrets to that file, and Wireshark reads it to decrypt the
traffic. This exposes only the ephemeral keys of those sessions, never
the server's private key.
