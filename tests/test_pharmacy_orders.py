"""
Pruebas funcionales para las tools de sintomas y pedidos.

El estado de los pedidos se escribe en data/orders.json; este script
apunta el almacen de datos a un directorio temporal para que el archivo
real nunca se toque.

Ejecutar con:  python tests/test_pharmacy_orders.py
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.tools import data_store as db  # noqa: E402


def check(label: str, condition: bool) -> bool:
    print(f"[{'OK ' if condition else 'FAIL'}] {label}")
    return condition


def main() -> int:
    # Redirigir la persistencia de pedidos a un archivo temporal, y
    # recargar el inventario desde disco para que los decrementos de
    # esta corrida empiecen desde los numeros ficticios completos y no
    # dependan del orden de las pruebas.
    tmp = tempfile.mkdtemp()
    db.ORDERS_PATH = os.path.join(tmp, "orders.json")
    db._inventory = None  # forzar recarga

    from server.tools import pharmacy_symptoms as sym
    from server.tools import pharmacy_orders as orders

    results = []

    # --- suggest_products_for_symptom ---------------------------------
    otc = json.loads(sym.suggest_products_for_symptom(symptom="dolor de cabeza"))
    results.append(check("un sintoma comun retorna sugerencias, sin derivacion",
                         otc["referral"] is False and len(otc["suggestions"]) > 0))
    results.append(check("la sugerencia incluye un disclaimer",
                         "disclaimer" in otc))

    red = json.loads(sym.suggest_products_for_symptom(symptom="tengo dolor en el pecho"))
    results.append(check("SINTOMA DE ALARMA retorna derivacion y NINGUN producto",
                         red["referral"] is True and red["suggestions"] == []))
    results.append(check("el sintoma de alarma identifica la frase que coincidio",
                         red["matched_red_flag"] == "dolor en el pecho"))

    pregnancy = json.loads(sym.suggest_products_for_symptom(symptom="estoy en embarazo"))
    results.append(check("el embarazo se trata como derivacion",
                         pregnancy["referral"] is True))

    unknown = json.loads(sym.suggest_products_for_symptom(symptom="me duele la antena"))
    results.append(check("sintoma desconocido: sin derivacion, sin sugerencias",
                         unknown["referral"] is False and unknown["suggestions"] == []))

    # --- create_order --------------------------------------------------
    stock_before = db.get_stock("MED-001")["SUC-01"]["units"]
    created = json.loads(orders.create_order(
        branch_id="SUC-01",
        customer_name="Ana Lopez",
        items=[{"sku": "MED-001", "quantity": 2}, {"sku": "MED-009", "quantity": 1}],
    ))
    results.append(check("el pedido queda confirmado", created["status"] == "confirmed"))
    results.append(check("el id del pedido tiene el prefijo ORD-",
                         created["order_id"].startswith("ORD-")))
    expected_total = round(25.5 * 2 + 18.0 * 1, 2)
    results.append(check("el total se calcula correctamente",
                         created["total"] == expected_total))
    stock_after = db.get_stock("MED-001")["SUC-01"]["units"]
    results.append(check("las existencias se decrementaron",
                         stock_after == stock_before - 2))

    # un producto con receta debe ser rechazado
    try:
        orders.create_order(branch_id="SUC-01", customer_name="X",
                            items=[{"sku": "MED-011", "quantity": 1}])
        results.append(check("producto con receta rechazado", False))
    except ValueError:
        results.append(check("producto con receta rechazado", True))

    # stock insuficiente debe rechazarse y NO alterar las existencias
    stock_guard = db.get_stock("MED-003")["SUC-02"]["units"]  # 0 unidades
    try:
        orders.create_order(branch_id="SUC-02", customer_name="X",
                            items=[{"sku": "MED-003", "quantity": 1}])
        results.append(check("stock insuficiente rechazado", False))
    except ValueError:
        results.append(check("stock insuficiente rechazado", True))
    results.append(check("el pedido rechazado no altero el stock",
                         db.get_stock("MED-003")["SUC-02"]["units"] == stock_guard))

    # atomicidad: un articulo invalido cancela todo el pedido de varios items
    good_before = db.get_stock("MED-014")["SUC-01"]["units"]
    try:
        orders.create_order(branch_id="SUC-01", customer_name="X",
                            items=[{"sku": "MED-014", "quantity": 1},
                                   {"sku": "MED-999", "quantity": 1}])
        results.append(check("atomicidad: un item invalido cancela el pedido", False))
    except ValueError:
        results.append(check("atomicidad: un item invalido cancela el pedido", True))
    results.append(check("atomicidad: el item valido NO se cobro",
                         db.get_stock("MED-014")["SUC-01"]["units"] == good_before))

    # --- get_order_status ---------------------------------------------
    status = json.loads(orders.get_order_status(order_id=created["order_id"]))
    results.append(check("la consulta de estado retorna el mismo pedido",
                         status["order_id"] == created["order_id"]
                         and status["total"] == expected_total))
    results.append(check("la consulta de estado no distingue mayusculas",
                         json.loads(orders.get_order_status(
                             order_id=created["order_id"].lower()
                         ))["order_id"] == created["order_id"]))

    try:
        orders.get_order_status(order_id="ORD-99999")
        results.append(check("pedido desconocido lanza excepcion", False))
    except ValueError:
        results.append(check("pedido desconocido lanza excepcion", True))

    shutil.rmtree(tmp, ignore_errors=True)

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} verificaciones exitosas")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())