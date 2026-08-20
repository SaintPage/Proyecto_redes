"""
Pharmacy domain tools (part 3): order creation and status.

create_order validates the requested items against the catalog and the
branch inventory, computes the total in GTQ, decrements stock and
persists the order to data/orders.json so its state survives across
calls. get_order_status reads that persisted state back.

Prescription products are rejected here on purpose: an automated channel
should not dispense them without a verified prescription. This mirrors a
real constraint and gives the chatbot a clear rule to explain.
"""

import datetime
from typing import Any

from . import data_store as db
from .registry import tool

ORDER_PREFIX = "ORD"


def _new_order_id(store: dict) -> str:
    number = store.get("next_id", 1)
    store["next_id"] = number + 1
    return f"{ORDER_PREFIX}-{number:05d}"


@tool(
    name="create_order",
    description=(
        "Create a purchase order for one or more products at a given "
        "branch. Validates that each product exists, is over the counter "
        "and has enough stock, decrements the inventory and returns the "
        "order id with the itemized total in GTQ. Prescription-only "
        "products are rejected."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "branch_id": {
                "type": "string",
                "description": "Branch where the order is placed, e.g. 'SUC-01'.",
            },
            "customer_name": {
                "type": "string",
                "description": "Name of the customer placing the order.",
            },
            "items": {
                "type": "array",
                "description": "Products to purchase.",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "quantity": {"type": "integer"},
                    },
                    "required": ["sku", "quantity"],
                },
            },
        },
        "required": ["branch_id", "customer_name", "items"],
    },
)
def create_order(branch_id: str, customer_name: str, items: list) -> str:
    branch = db.find_branch(branch_id)
    if branch is None:
        valid = ", ".join(b["id"] for b in db.get_branches())
        raise ValueError(f"Unknown branch '{branch_id}'. Valid branches: {valid}")

    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty array")

    customer_name = (customer_name or "").strip()
    if not customer_name:
        raise ValueError("customer_name must not be empty")

    inventory = db.get_inventory()
    currency = inventory.get("currency", "GTQ")

    # --- Validate everything BEFORE mutating any stock ----------------
    # This keeps the operation atomic: either the whole order is valid
    # and applied, or nothing changes.
    validated: list[dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError("each item must be an object with sku and quantity")
        sku = str(entry.get("sku", "")).strip().upper()
        quantity = entry.get("quantity")

        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ValueError(f"quantity for '{sku}' must be a positive integer")

        medication = db.find_medication(sku)
        if medication is None:
            raise ValueError(f"Unknown SKU '{sku}'.")
        if medication["requires_prescription"]:
            raise ValueError(
                f"'{sku}' ({medication['name']}) requires a prescription and "
                "cannot be sold through the automated channel."
            )

        branch_stock = inventory["stock"].get(sku, {}).get(branch["id"])
        if branch_stock is None:
            raise ValueError(f"'{sku}' is not carried at {branch['id']}.")
        if branch_stock["units"] < quantity:
            raise ValueError(
                f"Not enough stock of '{sku}' at {branch['id']}: "
                f"requested {quantity}, available {branch_stock['units']}."
            )

        validated.append(
            {
                "sku": sku,
                "name": medication["name"],
                "quantity": quantity,
                "unit_price": branch_stock["price"],
                "subtotal": round(branch_stock["price"] * quantity, 2),
                "_stock_ref": branch_stock,
            }
        )

    # --- Apply: decrement stock and build the order line items --------
    line_items = []
    total = 0.0
    for item in validated:
        item["_stock_ref"]["units"] -= item["quantity"]
        total += item["subtotal"]
        line_items.append(
            {
                "sku": item["sku"],
                "name": item["name"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "subtotal": item["subtotal"],
            }
        )

    with db.orders_lock():
        store = db.load_orders()
        order_id = _new_order_id(store)
        order = {
            "order_id": order_id,
            "branch_id": branch["id"],
            "branch_name": branch["name"],
            "customer_name": customer_name,
            "items": line_items,
            "currency": currency,
            "total": round(total, 2),
            "status": "confirmed",
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        store["orders"][order_id] = order
        db.save_orders(store)

    return db.as_json(
        {
            "order_id": order_id,
            "status": "confirmed",
            "branch": branch["name"],
            "customer_name": customer_name,
            "currency": currency,
            "items": line_items,
            "total": round(total, 2),
            "message": f"Pedido {order_id} confirmado. Total: {round(total, 2)} {currency}.",
        }
    )


@tool(
    name="get_order_status",
    description=(
        "Look up an existing order by its id and return its current "
        "status, items and total. Use the order id returned by "
        "create_order, e.g. 'ORD-00001'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "Order identifier, e.g. 'ORD-00001'.",
            },
        },
        "required": ["order_id"],
    },
)
def get_order_status(order_id: str) -> str:
    order_id = (order_id or "").strip().upper()
    store = db.load_orders()
    order = store.get("orders", {}).get(order_id)

    if order is None:
        raise ValueError(f"Order '{order_id}' not found.")

    return db.as_json(
        {
            "order_id": order["order_id"],
            "status": order["status"],
            "branch": order["branch_name"],
            "customer_name": order["customer_name"],
            "currency": order["currency"],
            "items": order["items"],
            "total": order["total"],
            "created_at": order["created_at"],
        }
    )
