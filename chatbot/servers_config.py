"""
Configuracion de los servidores MCP que levanta el anfitrion.

Aqui se definen los tres servidores del proyecto:

  * pharmacy   -> el servidor propio (funcionalidad 5)
  * filesystem -> servidor oficial de Anthropic (funcionalidad 4)
  * git        -> servidor oficial de Anthropic (funcionalidad 4)

Los dos oficiales trabajan sobre un directorio aislado (demo/) para que
el chatbot no pueda tocar el resto del proyecto por accidente. El
servidor de Filesystem recibe ese directorio como argumento y rechaza
cualquier ruta fuera de el.
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directorio de trabajo para la demostracion de la funcionalidad 4.
# Esta en .gitignore: es un sandbox, no forma parte del proyecto.
DEMO_DIR = os.path.join(ROOT, "demo")

IS_WINDOWS = sys.platform == "win32"


def npx_command(args: list[str]) -> list[str]:
    """
    Arma el comando para un servidor MCP publicado en npm.

    En Windows, npx es un script .cmd y no se puede ejecutar
    directamente con subprocess: hay que invocarlo a traves de cmd /c.
    """
    if IS_WINDOWS:
        return ["cmd", "/c", "npx", *args]
    return ["npx", *args]


def ensure_demo_repo() -> tuple[bool, str]:
    """
    Prepara el sandbox de la demostracion.

    Crea demo/ y lo inicializa como repositorio git si aun no lo es.

    Nota importante para el reporte: la version actual del servidor Git
    oficial (mcp-server-git) NO expone una herramienta git_init; solo
    opera sobre repositorios que ya existen. Por eso la creacion del
    repositorio la hace el anfitrion al preparar el espacio de trabajo,
    y todo lo demas (status, add, commit, log) si pasa por el servidor
    MCP oficial.

    Retorna (listo, mensaje).
    """
    os.makedirs(DEMO_DIR, exist_ok=True)

    if os.path.isdir(os.path.join(DEMO_DIR, ".git")):
        return True, f"repositorio ya existe en {DEMO_DIR}"

    if shutil.which("git") is None:
        return False, "git no esta instalado o no esta en el PATH"

    try:
        subprocess.run(["git", "init", "-b", "main", DEMO_DIR],
                       check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        return False, f"no se pudo inicializar el repositorio: {exc.stderr.strip()}"

    # Identidad local, para que git_commit no falle si la global no
    # esta configurada en la maquina. Es best-effort: si falla, el
    # repositorio igual sirve siempre que exista una identidad global.
    for key, value in (("user.email", "chatbot@uvg.edu.gt"),
                       ("user.name", "MCP Chatbot")):
        try:
            subprocess.run(["git", "-C", DEMO_DIR, "config", key, value],
                           check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            pass

    return True, f"repositorio inicializado en {DEMO_DIR}"


def get_servers() -> dict[str, list[str]]:
    """
    Retorna el comando de arranque de cada servidor MCP por stdio.

    - pharmacy: modulo propio, se ejecuta con el mismo interprete.
    - filesystem: paquete de npm, se ejecuta con npx (requiere Node.js).
    - git: paquete de PyPI, se ejecuta como modulo de Python
      (requiere: pip install mcp-server-git).
    """
    return {
        "pharmacy": [sys.executable, "-m", "server.main"],
        "filesystem": npx_command([
            "-y", "@modelcontextprotocol/server-filesystem", DEMO_DIR,
        ]),
        "git": [sys.executable, "-m", "mcp_server_git"],
    }


def get_remote_servers() -> dict[str, str]:
    """
    Retorna los servidores MCP remotos, por URL (funcionalidad 6).

    Se activan con la variable de entorno MCP_REMOTE_URL, que apunta a
    la raiz del servidor desplegado, por ejemplo:

        PowerShell:  $env:MCP_REMOTE_URL="https://mi-servidor.run.app"
        Git Bash:    export MCP_REMOTE_URL="https://mi-servidor.run.app"

    Para probar en local antes de desplegar, se levanta el servidor con
    "python -m server.main_http" y se usa http://127.0.0.1:8080.

    Cuando hay un servidor remoto configurado, el anfitrion lo usa EN
    LUGAR del de farmacia local: son el mismo servidor, y tener ambos
    duplicaria las herramientas.
    """
    url = os.environ.get("MCP_REMOTE_URL", "").strip()
    if not url:
        return {}
    return {"pharmacy": url}
