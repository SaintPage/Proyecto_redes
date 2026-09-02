"""
Prueba del escenario de la funcionalidad 4.

Verifica que el anfitrion puede usar los servidores MCP oficiales de
Anthropic (Filesystem y Git) para el escenario que pide el enunciado:
crear un repositorio, crear un README, agregarlo y hacer commit.

No requiere API key: ejecuta las herramientas directamente a traves del
cliente MCP, sin pasar por el LLM. Esto aisla la capa de protocolo del
comportamiento del modelo.

Requisitos previos:
    - Node.js instalado (para el servidor de Filesystem via npx)
    - pip install mcp-server-git (para el servidor de Git)

Ejecutar con:  python tests/test_official_servers.py
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from chatbot.mcp_client import MCPClient, MCPClientError  # noqa: E402
from chatbot.mcp_log import MCPLog  # noqa: E402
from chatbot.servers_config import (  # noqa: E402
    DEMO_DIR, ensure_demo_repo, get_servers,
)


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "OK " if condition else "FAIL"
    suffix = f"  {detail}" if detail and not condition else ""
    print(f"[{mark}] {label}{suffix}")
    return condition


def main() -> int:
    results = []
    log = MCPLog(echo=False)
    servers = get_servers()

    # Sandbox limpio para que la prueba sea reproducible.
    if os.path.isdir(DEMO_DIR):
        shutil.rmtree(DEMO_DIR, ignore_errors=True)
    ready, message = ensure_demo_repo()
    results.append(check("el sandbox queda listo como repositorio git",
                         ready, message))
    if not ready:
        return 1

    fs = MCPClient("filesystem", servers["filesystem"], log)
    git = MCPClient("git", servers["git"], log)

    try:
        try:
            fs.start()
        except (MCPClientError, OSError) as exc:
            print(f"[FAIL] no se pudo iniciar el servidor Filesystem: {exc}")
            print("       Requiere Node.js. Verifica con: node --version")
            return 1

        try:
            git.start()
        except (MCPClientError, OSError) as exc:
            print(f"[FAIL] no se pudo iniciar el servidor Git: {exc}")
            print("       Instalalo con: pip install mcp-server-git")
            fs.stop()
            return 1

        results.append(check("el servidor Filesystem expone herramientas",
                             len(fs.tools) > 0))
        results.append(check("el servidor Git expone herramientas",
                             len(git.tools) > 0))

        fs_names = {t["name"] for t in fs.tools}
        git_names = {t["name"] for t in git.tools}
        results.append(check("Filesystem ofrece write_file y list_directory",
                             {"write_file", "list_directory"} <= fs_names))
        results.append(check("Git ofrece git_add, git_commit y git_status",
                             {"git_add", "git_commit", "git_status"} <= git_names))

        readme = os.path.join(DEMO_DIR, "README.md")

        # --- el escenario del enunciado, paso por paso ----------------
        text, err = fs.call_tool("write_file", {
            "path": readme,
            "content": "# Proyecto Demo\n\nRepositorio creado por el chatbot MCP.\n",
        })
        results.append(check("1. crear README con el servidor Filesystem",
                             not err, text))
        results.append(check("   el archivo existe en disco",
                             os.path.isfile(readme)))

        text, err = git.call_tool("git_status", {"repo_path": DEMO_DIR})
        results.append(check("2. git_status ve el archivo sin rastrear",
                             not err and "README.md" in text, text))

        text, err = git.call_tool("git_add", {
            "repo_path": DEMO_DIR, "files": ["README.md"],
        })
        results.append(check("3. git_add agrega el archivo", not err, text))

        text, err = git.call_tool("git_commit", {
            "repo_path": DEMO_DIR, "message": "Add README via MCP chatbot",
        })
        results.append(check("4. git_commit crea el commit", not err, text))

        text, err = git.call_tool("git_log", {"repo_path": DEMO_DIR})
        results.append(check("5. git_log muestra el commit en el historial",
                             not err and "README" in text, text))

        # --- el sandbox realmente aisla -------------------------------
        text, err = fs.call_tool("write_file", {
            "path": os.path.join(ROOT, "fuera_del_sandbox.txt"),
            "content": "no deberia escribirse",
        })
        results.append(check("el servidor rechaza escribir fuera del sandbox",
                             err is True))
        results.append(check("   y el archivo no se creo",
                             not os.path.exists(
                                 os.path.join(ROOT, "fuera_del_sandbox.txt"))))

        # --- el log registro todo (funcionalidad 3) -------------------
        by_server = {e["server"] for e in log.entries}
        results.append(check("el log registra ambos servidores oficiales",
                             {"filesystem", "git"} <= by_server))

    finally:
        fs.stop()
        git.stop()

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} verificaciones exitosas")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
