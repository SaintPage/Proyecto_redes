"""
TEMPORARY tool, used only to verify the end-to-end pipeline.

Replace this module with the real domain tools once the industry use
case is approved. The registry mechanism stays exactly the same: import
the new module in server/tools/__init__.py and the tools show up in
tools/list automatically.
"""

from .registry import tool


@tool(
    name="echo",
    description=(
        "Returns the text it receives. Placeholder tool used to verify "
        "that the JSON-RPC pipeline works end to end."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to echo back"},
        },
        "required": ["text"],
    },
)
def echo(text: str) -> str:
    return f"echo: {text}"
