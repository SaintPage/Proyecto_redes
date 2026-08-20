"""
Tool registry.

Each MCP tool is a plain Python function decorated with @tool(). The
decorator stores the metadata that `tools/list` must expose (name,
description and JSON Schema for the arguments) plus the callable that
`tools/call` will execute.

Adding a new tool therefore requires no changes to the protocol layer.
"""

from typing import Any, Callable, Optional

# name -> {"name", "description", "inputSchema", "handler"}
_REGISTRY: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, input_schema: dict) -> Callable:
    """
    Register a function as an MCP tool.

    `input_schema` must be a JSON Schema object describing the arguments.
    The LLM relies on `description` and on the schema to decide when and
    how to call the tool, so both should be written carefully.
    """

    def decorator(func: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"Duplicated tool name: {name}")
        _REGISTRY[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": func,
        }
        return func

    return decorator


def list_tools() -> list[dict]:
    """Return the tool definitions in the shape required by tools/list."""
    return [
        {
            "name": meta["name"],
            "description": meta["description"],
            "inputSchema": meta["inputSchema"],
        }
        for meta in _REGISTRY.values()
    ]


def get_tool(name: str) -> Optional[dict]:
    """Return the registry entry for `name`, or None if it is unknown."""
    return _REGISTRY.get(name)


def validate_arguments(schema: dict, arguments: dict) -> Optional[str]:
    """
    Minimal JSON Schema check: required members and primitive types.

    A full validator (jsonschema) is not used on purpose, to keep the
    server dependency-free. This covers the cases the LLM actually hits.
    """
    if not isinstance(arguments, dict):
        return "arguments must be an object"

    for key in schema.get("required", []):
        if key not in arguments:
            return f"Missing required argument: {key}"

    types = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, value in arguments.items():
        prop = schema.get("properties", {}).get(key)
        if not prop:
            continue  # unknown members are ignored, not rejected
        expected = types.get(prop.get("type"))
        # bool is a subclass of int in Python; guard against it explicitly
        if expected and (
            not isinstance(value, expected)
            or (prop.get("type") in ("number", "integer") and isinstance(value, bool))
        ):
            return f"Argument '{key}' must be of type {prop.get('type')}"
    return None
