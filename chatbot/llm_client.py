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
import time

try:
    from google import genai
    from google.genai import types
    from google.genai import errors as genai_errors
except ImportError:  # pragma: no cover
    print("Falta el paquete 'google-genai'. Instalalo con:\n"
          "    pip install google-genai", file=sys.stderr)
    raise


class LLMUnavailableError(Exception):
    """El modelo no respondio despues de agotar los reintentos."""


# Codigos HTTP que vale la pena reintentar: son fallos transitorios del
# servicio, no errores de nuestra peticion.
#   429 -> se excedio la cuota por minuto
#   500 -> error interno del proveedor
#   503 -> el modelo esta saturado de demanda
RETRYABLE_STATUS = {429, 500, 503}
MAX_ATTEMPTS = 4
BASE_DELAY = 2.0  # segundos; se duplica en cada reintento

# Modelo por defecto. La familia Flash es la que cubre el nivel
# gratuito de la API de Gemini. Se puede cambiar con la variable de
# entorno GEMINI_MODEL si el modelo por defecto no esta disponible
# para tu llave (usa scripts/list_models.py para ver cuales tenes).
DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = (
    "Eres el asistente de una cadena de farmacias en Guatemala, y "
    "ademas tenes acceso a herramientas de archivos y de control de "
    "versiones para tareas tecnicas.\n\n"
    "Sobre la farmacia:\n"
    "- Usa las herramientas pharmacy__* cuando la pregunta sea sobre "
    "productos, existencias, sintomas o pedidos. No inventes datos de "
    "catalogo, precios ni disponibilidad.\n"
    "- Si una herramienta indica que se requiere atencion medica, "
    "transmite ese mensaje al usuario y no sugieras productos.\n"
    "- Nunca das diagnosticos. Recuerda al usuario consultar al "
    "farmaceutico cuando corresponda.\n"
    "- Los precios estan en quetzales (GTQ).\n\n"
    "Sobre archivos y git:\n"
    "- Las herramientas filesystem__* trabajan unicamente dentro del "
    "directorio de trabajo autorizado. Si necesitas saber cual es, usa "
    "filesystem__list_allowed_directories.\n"
    "- Las herramientas git__* requieren el parametro repo_path con la "
    "ruta del repositorio, que es ese mismo directorio de trabajo.\n"
    "- Para crear un archivo y versionarlo: primero escribilo con "
    "filesystem__write_file, luego git__git_add, y despues "
    "git__git_commit.\n"
    "- Usa rutas absolutas dentro del directorio autorizado."
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

    def __init__(self, model: str = "", system_prompt: str = SYSTEM_PROMPT,
                 on_retry=None) -> None:
        """
        `on_retry` es un callback opcional que se invoca antes de cada
        reintento, para que la interfaz pueda avisarle al usuario que
        se esta esperando en vez de quedarse muda.
        """
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
        self.on_retry = on_retry

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

        Los fallos transitorios del servicio (429, 500, 503) se
        reintentan con espera exponencial. Un servicio compartido puede
        saturarse en cualquier momento, asi que el cliente no debe
        asumir que cada llamada va a funcionar a la primera.
        """
        config_args = {
            "system_instruction": self.system_prompt,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        }
        if declarations:
            config_args["tools"] = [types.Tool(function_declarations=declarations)]

        config = types.GenerateContentConfig(**config_args)
        last_error: Exception | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except genai_errors.APIError as exc:
                status = getattr(exc, "code", None)
                if status not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                    raise
                last_error = exc
                delay = BASE_DELAY * (2 ** (attempt - 1))
                if self.on_retry:
                    self.on_retry(attempt, MAX_ATTEMPTS, delay, status)
                time.sleep(delay)

        raise LLMUnavailableError(
            f"El modelo no respondio tras {MAX_ATTEMPTS} intentos: {last_error}"
        )
