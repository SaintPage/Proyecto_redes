"""
Prueba de extremo a extremo del ciclo de vida de MCP.

Lanza el servidor como subproceso, exactamente como lo haria un cliente
MCP real, y recorre la secuencia completa:

    initialize -> notifications/initialized -> tools/list -> tools/call

Tambien verifica dos reglas de protocolo faciles de pasar por alto: no
se debe responder a las notificaciones, y un JSON malformado debe
producir un error -32700.

Ejecutar con:  python tests/test_handshake.py
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUESTS = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.1.0"},
        },
    },
    # Notificacion: el servidor NO debe enviar nada de vuelta para esta.
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "search_medications",
            "arguments": {"query": "ibuprofeno"},
        },
    },
    # Metodo desconocido -> -32601
    {"jsonrpc": "2.0", "id": 4, "method": "does/not/exist"},
    # Falta un argumento requerido -> -32602
    {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "check_inventory", "arguments": {}},
    },
]


def main() -> int:
    payload = "\n".join(json.dumps(r) for r in REQUESTS)
    payload += '\n{ this is not valid json }\n'  # -> -32700

    process = subprocess.run(
        [sys.executable, "-m", "server.main"],
        input=payload,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    responses = [json.loads(line) for line in process.stdout.splitlines() if line.strip()]

    print("=== Respuestas del servidor ===")
    for response in responses:
        print(json.dumps(response, indent=2, ensure_ascii=False))

    ids = [r.get("id") for r in responses]
    checks = [
        ("6 respuestas (la notificacion no se responde)", len(responses) == 6),
        ("sin respuesta con id=None de la notificacion", ids[:5] == [1, 2, 3, 4, 5]),
        ("initialize retorna serverInfo", "serverInfo" in responses[0].get("result", {})),
        ("tools/list retorna al menos una tool", len(responses[1]["result"]["tools"]) >= 1),
        ("tools/call retorna content", "content" in responses[2].get("result", {})),
        ("metodo desconocido -> -32601", responses[3]["error"]["code"] == -32601),
        ("argumentos invalidos -> -32602", responses[4]["error"]["code"] == -32602),
        ("JSON malformado -> -32700", responses[5]["error"]["code"] == -32700),
    ]

    print("\n=== Verificaciones ===")
    failed = 0
    for label, passed in checks:
        print(f"[{'OK ' if passed else 'FAIL'}] {label}")
        failed += 0 if passed else 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())