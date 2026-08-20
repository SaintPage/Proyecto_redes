"""
stdio transport for MCP.

MCP over stdio uses newline-delimited JSON: every message is a single
JSON object written on one line, terminated by "\\n". Messages MUST NOT
contain embedded newlines.

IMPORTANT: stdout is a protocol channel. Anything printed there that is
not a valid JSON-RPC message will corrupt the stream and break the client.
All diagnostics go to stderr instead (see logger.py).

This class is intentionally small so that Part 2 of the project can swap
it for an HTTP transport without touching the protocol logic.
"""

import json
import sys
from typing import Iterator, Optional


class StdioTransport:
    """Reads and writes newline-delimited JSON over stdin/stdout."""

    def __init__(self, stdin=None, stdout=None) -> None:
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout

    def receive(self) -> Iterator[tuple[Optional[dict], Optional[str]]]:
        """
        Yield (message, error) pairs, one per incoming line.

        If a line is not valid JSON, `message` is None and `error` holds
        the reason, so the caller can answer with a -32700 Parse error.
        Blank lines are ignored.
        """
        for line in self._stdin:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), None
            except json.JSONDecodeError as exc:
                yield None, str(exc)

    def send(self, message: dict) -> None:
        """Serialize and write one message, then flush immediately."""
        # separators without spaces keeps the frame compact;
        # ensure_ascii=False lets us send accents without escaping.
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
        self._stdout.write(data + "\n")
        self._stdout.flush()  # without this the client hangs waiting
