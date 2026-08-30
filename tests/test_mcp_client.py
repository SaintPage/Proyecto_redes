"""
Prueba del cliente MCP del anfitrion contra el servidor de farmacia.

No requiere API key: verifica unicamente la capa de comunicacion entre
el cliente y el servidor (funcionalidad 3 y la parte de la 5 que exige
que el servidor sea utilizado por el chatbot).

Ejecutar con:  python tests/test_mcp_client.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from chatbot.mcp_client import MCPClient, MCPClientError  # noqa: E402
from chatbot.mcp_log import MCPLog  # noqa: E402


def check(label: str, condition: bool) -> bool:
    print(f"[{'OK ' if condition else 'FAIL'}] {label}")
    return condition


def main() -> int:
    results = []
    # echo=False para que la salida del test quede limpia
    log = MCPLog(echo=False)
    client = MCPClient("pharmacy", [sys.executable, "-m", "server.main"], log)

    original_cwd = os.getcwd()
    os.chdir(ROOT)

    try:
        info = client.start()
        results.append(check("el handshake completa y devuelve serverInfo",
                             "serverInfo" in info))
        results.append(check("el servidor reporta sus 5 herramientas",
                             len(client.tools) == 5))

        names = {tool["name"] for tool in client.tools}
        results.append(check("las 5 tools esperadas estan presentes",
                             names == {"search_medications", "check_inventory",
                                       "suggest_products_for_symptom",
                                       "create_order", "get_order_status"}))

        # --- llamada real a una tool ---------------------------------
        text, is_error = client.call_tool("search_medications", {"query": "ibuprofeno"})
        payload = json.loads(text)
        results.append(check("call_tool devuelve resultado sin error",
                             is_error is False))
        results.append(check("la busqueda encuentra MED-002",
                             any(r["sku"] == "MED-002" for r in payload["results"])))

        # --- sintoma de alarma ----------------------------------------
        text, is_error = client.call_tool("suggest_products_for_symptom",
                                          {"symptom": "tengo dolor en el pecho"})
        payload = json.loads(text)
        results.append(check("sintoma de alarma se propaga por el protocolo",
                             payload["referral"] is True and payload["suggestions"] == []))

        # --- error de ejecucion de tool -------------------------------
        text, is_error = client.call_tool("get_order_status", {"order_id": "ORD-99999"})
        results.append(check("error de tool llega con isError=true",
                             is_error is True))

        # --- error de protocolo ---------------------------------------
        try:
            client.call_tool("no_existe", {})
            results.append(check("tool desconocida lanza MCPClientError", False))
        except MCPClientError:
            results.append(check("tool desconocida lanza MCPClientError", True))

        # --- log de interacciones (funcionalidad 3) --------------------
        requests = [e for e in log.entries if e["direction"] == "request"]
        responses = [e for e in log.entries if e["direction"] == "response"]
        notifications = [e for e in log.entries if e["direction"] == "notification"]

        results.append(check("el log registro solicitudes", len(requests) >= 6))
        results.append(check("el log registro respuestas", len(responses) >= 6))
        results.append(check("el log registro la notificacion del handshake",
                             len(notifications) == 1))
        results.append(check("solicitudes y respuestas quedan emparejadas",
                             len(requests) == len(responses)))

    finally:
        client.stop()
        os.chdir(original_cwd)

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} verificaciones exitosas")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
