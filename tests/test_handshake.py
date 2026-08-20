"""
End-to-end test of the MCP lifecycle.

Launches the server as a subprocess, exactly like a real MCP client
would, and walks through the full sequence:

    initialize -> notifications/initialized -> tools/list -> tools/call

It also checks two protocol rules that are easy to get wrong:
notifications must not be answered, and malformed JSON must produce a
-32700 Parse error.

Run with:  python tests/test_handshake.py
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
    # Notification: the server must NOT send anything back for this one.
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": "hola redes"}},
    },
    # Unknown method -> -32601
    {"jsonrpc": "2.0", "id": 4, "method": "does/not/exist"},
    # Missing required argument -> -32602
    {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {}},
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

    print("=== Server responses ===")
    for response in responses:
        print(json.dumps(response, indent=2, ensure_ascii=False))

    ids = [r.get("id") for r in responses]
    checks = [
        ("6 responses (the notification is not answered)", len(responses) == 6),
        ("no response with id=None from the notification", ids[:5] == [1, 2, 3, 4, 5]),
        ("initialize returns serverInfo", "serverInfo" in responses[0].get("result", {})),
        ("tools/list returns at least one tool", len(responses[1]["result"]["tools"]) >= 1),
        ("tools/call returns content", "content" in responses[2].get("result", {})),
        ("unknown method -> -32601", responses[3]["error"]["code"] == -32601),
        ("invalid arguments -> -32602", responses[4]["error"]["code"] == -32602),
        ("malformed JSON -> -32700", responses[5]["error"]["code"] == -32700),
    ]

    print("\n=== Checks ===")
    failed = 0
    for label, passed in checks:
        print(f"[{'OK ' if passed else 'FAIL'}] {label}")
        failed += 0 if passed else 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
