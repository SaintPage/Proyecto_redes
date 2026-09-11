"""
Prueba del servidor MCP remoto sobre HTTP (funcionalidad 6).

Levanta el servidor HTTP en un hilo, lo consulta con el cliente HTTP y
verifica que se comporta igual que el servidor local por stdio: mismo
handshake, mismas herramientas, mismos resultados y mismos codigos de
error.

Tambien comprueba los detalles propios del transporte HTTP: el codigo
202 para las notificaciones, el encabezado de sesion, y el endpoint de
salud que usan las plataformas de nube.

No requiere API key ni despliegue: todo corre en localhost.

Ejecutar con:  python tests/test_http_server.py
"""

import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from chatbot.mcp_client import MCPClientError  # noqa: E402
from chatbot.mcp_http_client import MCPHTTPClient  # noqa: E402
from chatbot.mcp_log import MCPLog  # noqa: E402
from server.http_transport import MCPHTTPHandler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "OK " if condition else "FAIL"
    suffix = f"  {detail}" if detail and not condition else ""
    print(f"[{mark}] {label}{suffix}")
    return condition


def free_port() -> int:
    """Pide al sistema un puerto libre, para no chocar con otros."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    results = []
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    httpd = ThreadingHTTPServer(("127.0.0.1", port), MCPHTTPHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)  # dejar que el socket quede listo

    log = MCPLog(echo=False)
    client = MCPHTTPClient("pharmacy-remote", base, log)

    try:
        # --- endpoint de salud (lo usan las plataformas de nube) ------
        with urllib.request.urlopen(f"{base}/health", timeout=5) as response:
            health = json.loads(response.read())
        results.append(check("el endpoint /health responde",
                             health.get("status") == "ok", str(health)))
        results.append(check("   informa el transporte usado",
                             health.get("transport") == "streamable-http"))

        # --- handshake ------------------------------------------------
        info = client.start()
        results.append(check("el handshake completa y devuelve serverInfo",
                             "serverInfo" in info))
        results.append(check("el servidor asigna un id de sesion",
                             client.session_id is not None))
        results.append(check("expone las mismas 5 herramientas que el local",
                             len(client.tools) == 5))

        names = {tool["name"] for tool in client.tools}
        results.append(check("   y son exactamente las mismas",
                             names == {"search_medications", "check_inventory",
                                       "suggest_products_for_symptom",
                                       "create_order", "get_order_status"}))

        # --- una tool real --------------------------------------------
        text, is_error = client.call_tool("search_medications",
                                          {"query": "ibuprofeno"})
        payload = json.loads(text)
        results.append(check("call_tool funciona igual que por stdio",
                             not is_error
                             and any(r["sku"] == "MED-002"
                                     for r in payload["results"])))

        # --- la regla de negocio viaja intacta ------------------------
        text, _ = client.call_tool("suggest_products_for_symptom",
                                   {"symptom": "tengo dolor en el pecho"})
        payload = json.loads(text)
        results.append(check("el sintoma de alarma se propaga por HTTP",
                             payload["referral"] is True
                             and payload["suggestions"] == []))

        # --- errores ---------------------------------------------------
        text, is_error = client.call_tool("get_order_status",
                                          {"order_id": "ORD-99999"})
        results.append(check("error de tool llega con isError=true",
                             is_error is True))

        try:
            client.call_tool("no_existe", {})
            results.append(check("tool desconocida lanza MCPClientError", False))
        except MCPClientError:
            results.append(check("tool desconocida lanza MCPClientError", True))

        # --- detalles del transporte HTTP -----------------------------
        # Una notificacion debe responder 202 sin cuerpo.
        data = json.dumps({"jsonrpc": "2.0",
                           "method": "notifications/initialized"}).encode()
        request = urllib.request.Request(
            f"{base}/mcp", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
            body = response.read()
        results.append(check("una notificacion responde 202 sin cuerpo",
                             status == 202 and not body, f"status={status}"))

        # JSON malformado -> 400 con error -32700
        bad = urllib.request.Request(
            f"{base}/mcp", data=b"{ esto no es json }",
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(bad, timeout=5)
            results.append(check("JSON malformado responde error -32700", False))
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read())
            results.append(check("JSON malformado responde error -32700",
                                 exc.code == 400
                                 and payload["error"]["code"] == -32700))

        # Ruta desconocida -> 404
        try:
            urllib.request.urlopen(f"{base}/no-existe", timeout=5)
            results.append(check("una ruta desconocida responde 404", False))
        except urllib.error.HTTPError as exc:
            results.append(check("una ruta desconocida responde 404",
                                 exc.code == 404))

        # --- el log registro todo (funcionalidad 3) -------------------
        requests_logged = [e for e in log.entries if e["direction"] == "request"]
        responses_logged = [e for e in log.entries if e["direction"] == "response"]
        results.append(check("el log registra el trafico del servidor remoto",
                             len(requests_logged) >= 5
                             and len(responses_logged) >= 5))

        # --- cierre de sesion ------------------------------------------
        session = client.session_id
        client.stop()
        results.append(check("la sesion se cierra en el servidor",
                             client.session_id is None and session is not None))

    finally:
        httpd.shutdown()
        httpd.server_close()

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} verificaciones exitosas")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
