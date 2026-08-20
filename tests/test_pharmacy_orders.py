"""
Functional tests for the symptom and order tools.

Order state is written to data/orders.json; this script points the data
store at a temporary directory so the real file is never touched.

Run with:  python tests/test_pharmacy_orders.py
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
    # Redirect order persistence to a temp file, and reload inventory
    # from disk so stock decrements in this run start from the full
    # fictional numbers and do not depend on test ordering.
    tmp = tempfile.mkdtemp()
    db.ORDERS_PATH = os.path.join(tmp, "orders.json")
    db._inventory = None  # force reload

    from server.tools import pharmacy_symptoms as sym
    from server.tools import pharmacy_orders as orders

    results = []

    # --- suggest_products_for_symptom ---------------------------------
    otc = json.loads(sym.suggest_products_for_symptom(symptom="dolor de cabeza"))
    results.append(check("common symptom returns suggestions, no referral",
                         otc["referral"] is False and len(otc["suggestions"]) > 0))
    results.append(check("suggestion carries a disclaimer",
                         "disclaimer" in otc))

    red = json.loads(sym.suggest_products_for_symptom(symptom="tengo dolor en el pecho"))
    results.append(check("RED FLAG returns referral and NO products",
                         red["referral"] is True and red["suggestions"] == []))
    results.append(check("red flag identifies the matched phrase",
                         red["matched_red_flag"] == "dolor en el pecho"))

    pregnancy = json.loads(sym.suggest_products_for_symptom(symptom="estoy en embarazo"))
    results.append(check("pregnancy is treated as a referral",
                         pregnancy["referral"] is True))

    unknown = json.loads(sym.suggest_products_for_symptom(symptom="me duele la antena"))
    results.append(check("unknown symptom: no referral, no suggestions",
                         unknown["referral"] is False and unknown["suggestions"] == []))

    # --- create_order --------------------------------------------------
    stock_before = db.get_stock("MED-001")["SUC-01"]["units"]
    created = json.loads(orders.create_order(
        branch_id="SUC-01",
        customer_name="Ana Lopez",
        items=[{"sku": "MED-001", "quantity": 2}, {"sku": "MED-009", "quantity": 1}],
    ))
    results.append(check("order is confirmed", created["status"] == "confirmed"))
    results.append(check("order id has the ORD- prefix",
                         created["order_id"].startswith("ORD-")))
    expected_total = round(25.5 * 2 + 18.0 * 1, 2)
    results.append(check("total is computed correctly",
                         created["total"] == expected_total))
    stock_after = db.get_stock("MED-001")["SUC-01"]["units"]
    results.append(check("stock was decremented",
                         stock_after == stock_before - 2))

    # prescription product must be rejected
    try:
        orders.create_order(branch_id="SUC-01", customer_name="X",
                            items=[{"sku": "MED-011", "quantity": 1}])
        results.append(check("prescription product rejected", False))
    except ValueError:
        results.append(check("prescription product rejected", True))

    # insufficient stock must be rejected and NOT change stock
    stock_guard = db.get_stock("MED-003")["SUC-02"]["units"]  # 0 units
    try:
        orders.create_order(branch_id="SUC-02", customer_name="X",
                            items=[{"sku": "MED-003", "quantity": 1}])
        results.append(check("insufficient stock rejected", False))
    except ValueError:
        results.append(check("insufficient stock rejected", True))
    results.append(check("rejected order left stock unchanged",
                         db.get_stock("MED-003")["SUC-02"]["units"] == stock_guard))

    # atomicity: one bad item cancels the whole multi-item order
    good_before = db.get_stock("MED-014")["SUC-01"]["units"]
    try:
        orders.create_order(branch_id="SUC-01", customer_name="X",
                            items=[{"sku": "MED-014", "quantity": 1},
                                   {"sku": "MED-999", "quantity": 1}])
        results.append(check("atomic: bad item cancels order", False))
    except ValueError:
        results.append(check("atomic: bad item cancels order", True))
    results.append(check("atomic: valid item was NOT charged",
                         db.get_stock("MED-014")["SUC-01"]["units"] == good_before))

    # --- get_order_status ---------------------------------------------
    status = json.loads(orders.get_order_status(order_id=created["order_id"]))
    results.append(check("status lookup returns the same order",
                         status["order_id"] == created["order_id"]
                         and status["total"] == expected_total))
    results.append(check("status lookup is case-insensitive",
                         json.loads(orders.get_order_status(
                             order_id=created["order_id"].lower()
                         ))["order_id"] == created["order_id"]))

    try:
        orders.get_order_status(order_id="ORD-99999")
        results.append(check("unknown order raises", False))
    except ValueError:
        results.append(check("unknown order raises", True))

    shutil.rmtree(tmp, ignore_errors=True)

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
