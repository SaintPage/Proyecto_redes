"""
Registro de tools.

Cada tool de MCP es una funcion de Python normal decorada con @tool().
El decorador guarda los metadatos que tools/list debe exponer (nombre,
descripcion y JSON Schema de los argumentos) mas la funcion que
tools/call va a ejecutar.

Agregar una tool nueva por lo tanto no requiere cambios en la capa de
protocolo.
"""

from typing import Any, Callable, Optional

# nombre -> {"name", "description", "inputSchema", "handler"}
_REGISTRY: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, input_schema: dict) -> Callable:
    """
    Registra una funcion como tool de MCP.

    `input_schema` debe ser un objeto JSON Schema que describa los
    argumentos. El LLM se apoya en `description` y en el schema para
    decidir cuando y como llamar a la tool, asi que ambos deben
    escribirse con cuidado.
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
    """Retorna las definiciones de tools en la forma que requiere tools/list."""
    return [
        {
            "name": meta["name"],
            "description": meta["description"],
            "inputSchema": meta["inputSchema"],
        }
        for meta in _REGISTRY.values()
    ]


def get_tool(name: str) -> Optional[dict]:
    """Retorna la entrada del registro para `name`, o None si es desconocido."""
    return _REGISTRY.get(name)


def validate_arguments(schema: dict, arguments: dict) -> Optional[str]:
    """
    Validacion minima de JSON Schema: miembros requeridos y tipos
    primitivos.

    A proposito no se usa un validador completo (jsonschema), para
    mantener el servidor sin dependencias externas. Esto cubre los
    casos que el LLM realmente produce.
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
            continue  # los miembros desconocidos se ignoran, no se rechazan
        expected = types.get(prop.get("type"))
        # bool es subclase de int en Python; nos protegemos explicitamente
        if expected and (
            not isinstance(value, expected)
            or (prop.get("type") in ("number", "integer") and isinstance(value, bool))
        ):
            return f"Argument '{key}' must be of type {prop.get('type')}"
    return None