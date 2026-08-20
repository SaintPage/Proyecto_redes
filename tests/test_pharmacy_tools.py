"""
Pruebas funcionales para las tools de farmacia (busqueda e inventario).

Llaman directamente a las funciones de las tools (sin pasar por el
transporte), lo que las hace rapidas y facilita ubicar fallos. El lado
del protocolo esta cubierto por test_handshake.py.

Ejecutar con:  python tests/test_pharmacy_tools.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.tools import pharmacy  # noqa: E402


def check(label: str, condition: bool) -> bool:
    print(f"[{'OK ' if condition else 'FAIL'}] {label}")
    return condition


def main() -> int:
    results = []

    # --- search_medications -------------------------------------------
    found = json.loads(pharmacy.search_medications(query="ibuprofeno"))
    results.append(check("buscar por principio activo encuentra MED-002",
                         any(r["sku"] == "MED-002" for r in found["results"])))

    by_category = json.loads(pharmacy.search_medications(category="antibiotico"))
    results.append(check("el filtro de categoria retorna solo antibioticos",
                         all(r["category"] == "antibiotico" for r in by_category["results"])
                         and by_category["count"] > 0))

    otc = json.loads(pharmacy.search_medications(otc_only=True))
    results.append(check("otc_only excluye productos con receta",
                         all(not r["requires_prescription"] for r in otc["results"])))

    empty = json.loads(pharmacy.search_medications(query="zzzzz"))
    results.append(check("sin coincidencias retorna count 0", empty["count"] == 0))

    limited = json.loads(pharmacy.search_medications(limit=3))
    results.append(check("limit acota la lista de resultados",
                         limited["count"] == 3 and limited["truncated"] is True))

    try:
        pharmacy.search_medications(category="inventada")
        results.append(check("categoria invalida lanza excepcion", False))
    except ValueError:
        results.append(check("categoria invalida lanza excepcion", True))

    # --- check_inventory ----------------------------------------------
    inventory = json.loads(pharmacy.check_inventory(sku="MED-002"))
    results.append(check("el inventario lista las tres sucursales",
                         len(inventory["availability"]) == 3))

    one = json.loads(pharmacy.check_inventory(sku="MED-001", branch_id="SUC-03"))
    results.append(check("el filtro de sucursal retorna una sola sucursal",
                         len(one["availability"]) == 1
                         and one["availability"][0]["branch_id"] == "SUC-03"))
    results.append(check("una sucursal sin stock reporta in_stock false",
                         one["availability"][0]["in_stock"] is False))

    lower = json.loads(pharmacy.check_inventory(sku="med-002"))
    results.append(check("la busqueda de SKU no distingue mayusculas", lower["sku"] == "MED-002"))

    rx = json.loads(pharmacy.check_inventory(sku="MED-011"))
    results.append(check("se expone la bandera de receta",
                         rx["requires_prescription"] is True))

    try:
        pharmacy.check_inventory(sku="MED-999")
        results.append(check("SKU desconocido lanza excepcion", False))
    except ValueError:
        results.append(check("SKU desconocido lanza excepcion", True))

    try:
        pharmacy.check_inventory(sku="MED-001", branch_id="SUC-99")
        results.append(check("sucursal desconocida lanza excepcion", False))
    except ValueError:
        results.append(check("sucursal desconocida lanza excepcion", True))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} verificaciones exitosas")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())