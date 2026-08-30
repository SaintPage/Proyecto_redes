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
from .llm_client import LLMClient, mcp_tools_to_gemini
from .mcp_client import MCPClient, MCPClientError
from .mcp_log import MCPLog

BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

# Numero maximo de rondas de herramientas por turno, para evitar que un
# bucle de tool calls se quede dando vueltas indefinidamente.
MAX_TOOL_ROUNDS = 6

# Servidores MCP que el anfitrion levanta al iniciar. Mas adelante se
# agregaran aqui los servidores oficiales de Filesystem y Git.
SERVERS = {
    "pharmacy": [sys.executable, "-m", "server.main"],
}


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
        response = llm.send(conv.contents, declarations)
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
    print(f"{CYAN}Conectando servidores MCP...{RESET}")

    # --- levantar los servidores MCP ---------------------------------
    for name, command in SERVERS.items():
        client = MCPClient(name, command, log)
        try:
            client.start()
            clients[name] = client
            print(f"  {GREEN}OK{RESET} {name}: {len(client.tools)} herramientas")
        except (MCPClientError, OSError) as exc:
            print(f"  {RED}X{RESET} {name}: {exc}")

    if not clients:
        print(f"{RED}No se pudo conectar ningun servidor MCP.{RESET}")
        return 1

    # --- conectar el LLM ----------------------------------------------
    try:
        llm = LLMClient()
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
            except Exception as exc:  # noqa: BLE001
                print(f"\n{RED}Error en el turno: {exc}{RESET}\n")
                traceback.print_exc(file=sys.stderr)

    finally:
        print(f"\n{CYAN}{log.summary()}{RESET}")
        print(f"{CYAN}Cerrando servidores MCP...{RESET}")
        for client in clients.values():
            client.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())