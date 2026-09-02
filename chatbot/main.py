"""
Chatbot anfitrion (host) del proyecto.

Une las tres piezas del bloque 1:

  1. Conexion con el LLM a nivel de su API      -> llm_client.py
  2. Contexto de sesion                          -> conversation.py
  3. Log de interacciones con servidores MCP     -> mcp_log.py

Y ademas conecta el servidor MCP de farmacia (funcionalidad 5), que es
lo que le da al log algo que registrar y al LLM herramientas que usar.

Uso:
    python -m chatbot.main

Comandos dentro del chat:
    /tools    lista las herramientas disponibles
    /log      muestra el log completo de interacciones MCP
    /reset    borra el contexto de la conversacion
    /salir    termina la sesion
"""

import json
import sys
import traceback

from .conversation import Conversation
from .llm_client import LLMClient, LLMUnavailableError, mcp_tools_to_gemini
from .mcp_client import MCPClient, MCPClientError
from .mcp_log import MCPLog
from .servers_config import DEMO_DIR, ensure_demo_repo, get_servers

try:
    from google.genai import errors as genai_errors
except ImportError:  # pragma: no cover
    genai_errors = None

BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

# Numero maximo de rondas de herramientas por turno, para evitar que un
# bucle de tool calls se quede dando vueltas indefinidamente.
MAX_TOOL_ROUNDS = 6

# Con --debug se muestra el traceback completo de los errores. Sin el,
# solo el mensaje, que es lo apropiado durante una demostracion.
DEBUG = "--debug" in sys.argv


def build_tool_index(clients: dict) -> tuple[list, dict]:
    """
    Arma las function declarations para la API y el indice de ruteo.

    Retorna:
      - la lista de declarations (con nombre prefijado por servidor)
      - un diccionario nombre_prefijado -> (cliente, nombre_real)
    """
    declarations = []
    routing: dict[str, tuple] = {}

    for prefix, client in clients.items():
        declarations.extend(mcp_tools_to_gemini(client.tools, prefix))
        for tool in client.tools:
            routing[f"{prefix}__{tool['name']}"] = (client, tool["name"])

    return declarations, routing


def notify_retry(attempt: int, total: int, delay: float, status) -> None:
    """Avisa en consola que el servicio fallo y se va a reintentar."""
    reason = {
        429: "cuota por minuto excedida",
        500: "error interno del proveedor",
        503: "el modelo esta saturado",
    }.get(status, f"error {status}")
    print(f"{YELLOW}  ({reason}; reintento {attempt}/{total - 1} "
          f"en {delay:.0f}s...){RESET}")


def extract_parts(response) -> list:
    """Obtiene los bloques de la respuesta, tolerando respuestas vacias."""
    if not getattr(response, "candidates", None):
        return []
    content = response.candidates[0].content
    if content is None or not getattr(content, "parts", None):
        return []
    return list(content.parts)


def run_turn(llm: LLMClient, conv: Conversation, declarations: list,
             routing: dict) -> None:
    """
    Procesa un turno completo del usuario.

    El modelo puede pedir herramientas varias veces seguidas, asi que
    esto es un bucle: se llama al LLM, si pide tools se ejecutan, se le
    devuelven los resultados, y se vuelve a llamar hasta que responda
    con texto final.
    """
    for _ in range(MAX_TOOL_ROUNDS):
        # Cada turno con herramientas implica al menos dos llamadas a la
        # API, asi que conviene avisar que se esta trabajando.
        print(f"{YELLOW}  (pensando...){RESET}", end="\r", flush=True)
        response = llm.send(conv.contents, declarations)
        print(" " * 20, end="\r")  # borra el indicador
        parts = extract_parts(response)

        if not parts:
            print(f"\n{YELLOW}(el modelo no devolvio contenido){RESET}\n")
            return

        conv.add_model(parts)

        # Texto que el modelo produjo en este paso
        for part in parts:
            text = getattr(part, "text", None)
            if text and text.strip():
                print(f"\n{GREEN}Asistente:{RESET} {text.strip()}\n")

        # Llamadas a herramientas solicitadas por el modelo
        calls = [p.function_call for p in parts if getattr(p, "function_call", None)]
        if not calls:
            return  # el modelo termino, no pide mas herramientas

        results = []
        for call in calls:
            entry = routing.get(call.name)
            arguments = dict(call.args or {})

            if entry is None:
                results.append((call.name, {
                    "error": f"Herramienta desconocida: {call.name}",
                }))
                continue

            client, real_name = entry
            try:
                text, is_error = client.call_tool(real_name, arguments)
            except MCPClientError as exc:
                results.append((call.name, {"error": str(exc)}))
                continue

            # El resultado de la tool es JSON en texto; se intenta
            # entregar como objeto para que el modelo lo lea mejor.
            try:
                payload = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                payload = {"result": text}

            if is_error:
                results.append((call.name, {"error": text}))
            else:
                results.append((call.name, payload if isinstance(payload, dict)
                                else {"result": payload}))

        conv.add_tool_results(results)

    print(f"\n{YELLOW}(se alcanzo el limite de rondas de herramientas){RESET}\n")


def main() -> int:
    log = MCPLog(echo=True)
    clients: dict = {}

    print(f"{BOLD}Chatbot de farmacia — anfitrion MCP{RESET}")

    # --- preparar el sandbox de la demostracion (funcionalidad 4) -----
    ready, message = ensure_demo_repo()
    print(f"{CYAN}Espacio de trabajo: {message}{RESET}")
    if not ready:
        print(f"{YELLOW}  Las herramientas de git podrian fallar.{RESET}")

    print(f"{CYAN}Conectando servidores MCP...{RESET}")

    # --- levantar los servidores MCP ---------------------------------
    for name, command in get_servers().items():
        client = MCPClient(name, command, log)
        try:
            client.start()
            clients[name] = client
            print(f"  {GREEN}OK{RESET} {name}: {len(client.tools)} herramientas")
        except (MCPClientError, OSError) as exc:
            print(f"  {RED}X{RESET} {name}: {exc}")
            if name == "filesystem":
                print(f"     {YELLOW}Requiere Node.js. Verifica con: node --version{RESET}")
            elif name == "git":
                print(f"     {YELLOW}Instalalo con: pip install mcp-server-git{RESET}")

    if not clients:
        print(f"{RED}No se pudo conectar ningun servidor MCP.{RESET}")
        return 1

    # --- conectar el LLM ----------------------------------------------
    try:
        llm = LLMClient(on_retry=notify_retry)
    except RuntimeError as exc:
        print(f"\n{RED}{exc}{RESET}")
        for client in clients.values():
            client.stop()
        return 1

    print(f"  {GREEN}OK{RESET} LLM: {llm.model}")

    declarations, routing = build_tool_index(clients)
    conv = Conversation()

    print(f"\n{CYAN}Listo. Escribi tu mensaje, o /tools /log /reset /salir{RESET}\n")

    # --- bucle de conversacion ----------------------------------------
    try:
        while True:
            try:
                user_input = input(f"{BOLD}Vos:{RESET} ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input:
                continue

            if user_input in ("/salir", "/quit", "/exit"):
                break

            if user_input == "/tools":
                print(f"\n{CYAN}Herramientas disponibles ({len(declarations)}):{RESET}")
                for decl in declarations:
                    print(f"  - {decl.name}")
                    print(f"    {(decl.description or '')[:100]}...")
                print()
                continue

            if user_input == "/log":
                log.show()
                continue

            if user_input == "/reset":
                conv.reset()
                print(f"{YELLOW}Contexto borrado.{RESET}\n")
                continue

            conv.add_user(user_input)
            try:
                run_turn(llm, conv, declarations, routing)
            except LLMUnavailableError as exc:
                print(f"\n{RED}{exc}{RESET}")
                print(f"{YELLOW}Proba de nuevo en un momento, o cambia de "
                      f"modelo con GEMINI_MODEL.{RESET}\n")
            except Exception as exc:  # noqa: BLE001
                # Los errores de la API traen un mensaje util; el
                # traceback completo solo se muestra con --debug.
                if genai_errors and isinstance(exc, genai_errors.APIError):
                    print(f"\n{RED}Error de la API ({getattr(exc, 'code', '?')}): "
                          f"{getattr(exc, 'message', exc)}{RESET}\n")
                else:
                    print(f"\n{RED}Error en el turno: {exc}{RESET}\n")
                if DEBUG:
                    traceback.print_exc(file=sys.stderr)

    finally:
        print(f"\n{CYAN}{log.summary()}{RESET}")
        print(f"{CYAN}Cerrando servidores MCP...{RESET}")
        for client in clients.values():
            client.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
