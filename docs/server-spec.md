# MCP Server Specification — Pharmacy Chain

Report section 8. This document specifies the local MCP server built for
the project: its transport, protocol methods, and the tools it exposes
(parameters, return shape and usage examples).

The server is implemented manually on top of **JSON-RPC 2.0**, without
FastMCP or any MCP SDK.

---

## 1. Transport and framing

- **Transport:** standard input / standard output (stdio).
- **Framing:** newline-delimited JSON. One JSON-RPC message per line,
  terminated by `\n`. Messages contain no embedded newlines.
- **Channels:** `stdout` carries protocol messages only. All logging and
  diagnostics go to `stderr` and to `logs/server.log`.
- **Encoding:** UTF-8.

## 2. Protocol methods

The server implements the server side of the MCP lifecycle:

| Method | Type | Description |
|---|---|---|
| `initialize` | request | Version negotiation and capability exchange. |
| `notifications/initialized` | notification | Client confirms the handshake. No response is sent. |
| `tools/list` | request | Returns the catalog of available tools. |
| `tools/call` | request | Executes one tool by name. |
| `ping` | request | Liveness check; returns an empty result. |

### 2.1 initialize

Request `params`:

| Field | Type | Description |
|---|---|---|
| `protocolVersion` | string | Protocol revision requested by the client. |
| `capabilities` | object | Client capabilities. |
| `clientInfo` | object | `{ name, version }` of the client. |

Result:

```json
{
  "protocolVersion": "2025-06-18",
  "capabilities": { "tools": {} },
  "serverInfo": { "name": "custom-mcp-server", "version": "0.1.0" }
}
```

The server declares the `tools` capability. If the client requests a
protocol version the server recognizes, that version is echoed back;
otherwise the server answers with its own default (`2025-06-18`).

### 2.2 tools/call

Request `params`:

| Field | Type | Description |
|---|---|---|
| `name` | string | Name of the tool to execute. |
| `arguments` | object | Arguments matching the tool's input schema. |

Result: an MCP tool result object.

```json
{
  "content": [{ "type": "text", "text": "<tool output as JSON>" }],
  "isError": false
}
```

Tool output is itself returned as a JSON string inside the `text` field,
so the host can parse it or show it directly in the interaction log.

## 3. Error handling

Two distinct error channels, by design:

- **Protocol errors** use JSON-RPC error objects with standard codes:

  | Code | Meaning | When |
  |---|---|---|
  | `-32700` | Parse error | A line was not valid JSON. |
  | `-32600` | Invalid Request | Missing `jsonrpc`/`method`, wrong shape. |
  | `-32601` | Method not found | Unknown method. |
  | `-32602` | Invalid params | Unknown tool, or arguments fail schema validation. |
  | `-32603` | Internal error | Unexpected server-side exception. |

- **Tool execution errors** are NOT protocol errors. They come back as a
  normal result with `isError: true` and a human-readable message inside
  `content`, so the LLM can read the problem and react.

## 4. Tools

All data is fictional and stored under `data/`. Prices are in Guatemalan
Quetzales (**GTQ**). The catalog has 18 products across three branches
(`SUC-01` Mixco, `SUC-02` Zona 10, `SUC-03` Villa Nueva).

### 4.1 search_medications

Search the catalog by name, active ingredient or category.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | no | Free text matched against name and active ingredient. |
| `category` | string (enum) | no | One of the nine product categories. |
| `otc_only` | boolean | no | If true, exclude prescription products. |
| `limit` | integer | no | Max results, 1–50 (default 10). |

Returns `{ count, truncated, results[] }`, each result carrying `sku`,
`name`, `active_ingredient`, `category`, `presentation` and
`requires_prescription`.

**Example**

```json
// tools/call arguments
{ "name": "search_medications", "arguments": { "query": "ibuprofeno" } }

// result content (parsed)
{
  "count": 1,
  "truncated": false,
  "results": [
    {
      "sku": "MED-002",
      "name": "Ibuprofeno 400 mg",
      "active_ingredient": "ibuprofeno",
      "category": "antiinflamatorio",
      "presentation": "Tabletas, caja de 30",
      "requires_prescription": false
    }
  ]
}
```

### 4.2 check_inventory

Check availability and price of a product across branches.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sku` | string | yes | Product SKU, e.g. `MED-002`. |
| `branch_id` | string | no | Restrict to one branch, e.g. `SUC-01`. |

Returns the product, `currency`, `total_units` and an `availability[]`
array with per-branch `units`, `in_stock` and `price`.

**Example**

```json
{ "name": "check_inventory", "arguments": { "sku": "MED-002", "branch_id": "SUC-01" } }

{
  "sku": "MED-002",
  "name": "Ibuprofeno 400 mg",
  "requires_prescription": false,
  "currency": "GTQ",
  "total_units": 52,
  "availability": [
    {
      "branch_id": "SUC-01",
      "branch_name": "Sucursal Mixco",
      "address": "Calzada San Juan 12-45, Mixco",
      "hours": "07:00-21:00",
      "units": 52,
      "in_stock": true,
      "price": 38.0
    }
  ]
}
```

### 4.3 suggest_products_for_symptom

Map a plain-language symptom to OTC product categories. **Safety first:**
if the symptom matches a red flag (chest pain, trouble breathing,
pregnancy, infant symptoms, etc.), the tool returns a medical referral
and no products. Every non-referral response carries a disclaimer to
consult the pharmacist. The tool never diagnoses.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symptom` | string | yes | Symptom in plain language. |
| `max_products` | integer | no | Max products per category, 1–10 (default 3). |

Returns `{ symptom, referral, suggestions[] }`, plus `disclaimer` on
normal responses, or `matched_red_flag` and `message` on referrals.

**Example — normal**

```json
{ "name": "suggest_products_for_symptom", "arguments": { "symptom": "dolor de cabeza" } }

{
  "symptom": "dolor de cabeza",
  "referral": false,
  "disclaimer": "Esta es una sugerencia automatizada ... Consulte siempre al farmaceutico ...",
  "suggestions": [
    {
      "category": "analgesico",
      "products": [
        { "sku": "MED-001", "name": "Acetaminofen 500 mg", "presentation": "Tabletas, caja de 20" }
      ]
    }
  ]
}
```

**Example — red flag (referral)**

```json
{ "name": "suggest_products_for_symptom", "arguments": { "symptom": "tengo dolor en el pecho" } }

{
  "symptom": "tengo dolor en el pecho",
  "referral": true,
  "matched_red_flag": "dolor en el pecho",
  "message": "Los sintomas descritos pueden requerir atencion medica ...",
  "suggestions": []
}
```

### 4.4 create_order

Create a purchase order at a branch. Validates every item (exists, is
OTC, has enough stock) **before** modifying anything, so an order is
applied atomically or not at all. Prescription products are rejected.
On success, stock is decremented and the order is persisted.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `branch_id` | string | yes | Branch where the order is placed. |
| `customer_name` | string | yes | Customer name. |
| `items` | array | yes | List of `{ sku, quantity }` (quantity ≥ 1). |

Returns `order_id`, `status`, `branch`, itemized `items[]` with subtotal,
`total` and `currency`.

**Example**

```json
{
  "name": "create_order",
  "arguments": {
    "branch_id": "SUC-01",
    "customer_name": "Ana Lopez",
    "items": [
      { "sku": "MED-001", "quantity": 2 },
      { "sku": "MED-009", "quantity": 1 }
    ]
  }
}

{
  "order_id": "ORD-00001",
  "status": "confirmed",
  "branch": "Sucursal Mixco",
  "customer_name": "Ana Lopez",
  "currency": "GTQ",
  "items": [
    { "sku": "MED-001", "name": "Acetaminofen 500 mg", "quantity": 2, "unit_price": 25.5, "subtotal": 51.0 },
    { "sku": "MED-009", "name": "Sales de rehidratacion oral", "quantity": 1, "unit_price": 18.0, "subtotal": 18.0 }
  ],
  "total": 69.0,
  "message": "Pedido ORD-00001 confirmado. Total: 69.0 GTQ."
}
```

### 4.5 get_order_status

Look up an existing order by id.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `order_id` | string | yes | Order id from `create_order`, e.g. `ORD-00001`. |

Returns the stored order: `status`, `branch`, `items[]`, `total`,
`currency` and `created_at`. An unknown id is a tool error.

**Example**

```json
{ "name": "get_order_status", "arguments": { "order_id": "ORD-00001" } }

{
  "order_id": "ORD-00001",
  "status": "confirmed",
  "branch": "Sucursal Mixco",
  "customer_name": "Ana Lopez",
  "currency": "GTQ",
  "items": [ ... ],
  "total": 69.0,
  "created_at": "2026-08-20T14:03:11"
}
```

## 5. Data files

| File | Contents |
|---|---|
| `data/catalog.json` | 18 fictional products. |
| `data/inventory.json` | Three branches and per-branch stock/price. |
| `data/symptom_map.json` | OTC symptom→category map and red-flag list. |
| `data/orders.json` | Orders created at runtime (not in version control). |

## 6. How to run

The server is normally launched by an MCP client over stdio. To exercise
it by hand:

```bash
python -m server.main
```

then send, one JSON object per line:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0.1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_medications","arguments":{"query":"ibuprofeno"}}}
```

Automated checks:

```bash
python tests/test_handshake.py
python tests/test_pharmacy_tools.py
python tests/test_pharmacy_orders.py
```
