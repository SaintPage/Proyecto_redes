"""
Conexion con el LLM a nivel de su API (funcionalidad 1).

Usa el SDK oficial de Google para la API de Gemini. Ojo con la
restriccion del enunciado: lo que debe implementarse a mano es el
protocolo MCP (sin FastMCP ni SDKs de MCP). El SDK de Gemini es el
cliente HTTP del modelo, no una implementacion de MCP, por lo que su
uso si esta permitido.

Se eligio Gemini porque su nivel gratuito permite desarrollar el
proyecto sin costo. El enunciado sugiere los modelos de Anthropic por
sus creditos gratuitos, pero no los exige.

Este modulo tambien traduce las tools de MCP al formato de function
declarations de Gemini: ambos usan JSON Schema, asi que la conversion
es casi directa.
"""

import os
import sys

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover
    print("Falta el paquete 'google-genai'. Instalalo con:\n"
          "    pip install google-genai", file=sys.stderr)
    raise

# Modelo por defecto. La familia Flash es la que cubre el nivel
# gratuito de la API de Gemini. Se puede cambiar con la variable de
# entorno GEMINI_MODEL si el modelo por defecto no esta disponible
# para tu llave (usa scripts/list_models.py para ver cuales tenes).
DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = (
    "Eres el asistente de una cadena de farmacias en Guatemala. "
    "Puedes responder preguntas generales, y ademas tienes herramientas "
    "para consultar el catalogo, revisar inventario por sucursal, "
    "orientar sobre sintomas y gestionar pedidos.\n\n"
    "Reglas importantes:\n"
    "- Usa las herramientas cuando la pregunta sea sobre productos, "
    "existencias, sintomas o pedidos. No inventes datos de catalogo, "
    "precios ni disponibilidad.\n"
    "- Si una herramienta indica que se requiere atencion medica, "
    "transmite ese mensaje al usuario y no sugieras productos.\n"
    "- Nunca das diagnosticos. Recuerda al usuario consultar al "
    "farmaceutico cuando corresponda.\n"
    "- Los precios estan en quetzales (GTQ)."
)


def mcp_tools_to_gemini(tools: list[dict], prefix: str) -> list:
    """
    Convierte definiciones de tools de MCP a function declarations.

    Se antepone el nombre del servidor al nombre de la tool (por
    ejemplo, pharmacy__check_inventory) para que el anfitrion sepa a
    cual servidor enrutar la llamada cuando haya varios conectados.

    El inputSchema de MCP ya es JSON Schema, que es exactamente lo que
    espera parameters_json_schema, asi que no hay que reescribirlo.
    """
    declarations = []
    for tool in tools:
        schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
        declarations.append(
            types.FunctionDeclaration(
                name=f"{prefix}__{tool['name']}",
                description=tool.get("description", ""),
                parameters_json_schema=schema,
            )
        )
    return declarations


class LLMClient:
    """Envoltura minima sobre la API de Gemini."""

    def __init__(self, model: str = "", system_prompt: str = SYSTEM_PROMPT) -> None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Falta la variable de entorno GEMINI_API_KEY.\n"
                "Obtene una llave gratuita en https://aistudio.google.com/apikey "
                "y ejecuta:\n"
                '    PowerShell:  $env:GEMINI_API_KEY="tu-llave"\n'
                '    Git Bash:    export GEMINI_API_KEY="tu-llave"'
            )
        self.client = genai.Client(api_key=api_key)
        self.model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self.system_prompt = system_prompt

    def send(self, contents: list, declarations: list):
        """
        Envia el historial completo y retorna la respuesta del modelo.

        El historial va completo en cada llamada porque la API no
        guarda estado entre solicitudes: ahi es donde entra la clase
        Conversation (funcionalidad 2).

        La llamada automatica de funciones se desactiva a proposito:
        queremos ejecutar las tools nosotros, pasando por el cliente
        MCP, para que cada interaccion quede registrada en el log
        (funcionalidad 3).
        """
        config_args = {
            "system_instruction": self.system_prompt,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        }
        if declarations:
            config_args["tools"] = [types.Tool(function_declarations=declarations)]

        return self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(**config_args),
        )