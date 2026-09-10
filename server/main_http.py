"""
Punto de entrada del servidor MCP remoto (funcionalidad 6).

Es el equivalente de main.py, pero sirviendo el protocolo por HTTP en
lugar de stdio. Las herramientas y el nucleo del protocolo son
exactamente los mismos.

Uso local:
    python -m server.main_http
    python -m server.main_http --port 9000

En la nube, la plataforma define la variable PORT y el servidor la toma
automaticamente.
"""

import argparse
import sys

from .http_transport import serve


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Servidor MCP de farmacia sobre HTTP")
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Interfaz de escucha (por defecto 0.0.0.0)")
    parser.add_argument(
        "--port", type=int, default=None,
        help="Puerto; por defecto toma PORT del entorno, o 8080")
    args = parser.parse_args()

    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
