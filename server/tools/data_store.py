"""
Data access layer for the pharmacy MCP server.

Loads the fictional catalog and inventory from JSON files and keeps them
in memory. Orders are persisted back to disk so their state survives
between tool calls (and between sessions), which is what makes
`get_order_status` meaningful.

Keeping file I/O here means the tool functions stay small and readable.
"""

import json
import os
import threading
from typing import Any, Optional

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)

CATALOG_PATH = os.path.join(DATA_DIR, "catalog.json")
INVENTORY_PATH = os.path.join(DATA_DIR, "inventory.json")
ORDERS_PATH = os.path.join(DATA_DIR, "orders.json")
SYMPTOM_MAP_PATH = os.path.join(DATA_DIR, "symptom_map.json")

# Orders are written from tool calls; a lock avoids a corrupted file if
# two calls ever overlap.
_orders_lock = threading.Lock()

_catalog: Optional[dict] = None
_inventory: Optional[dict] = None
_symptom_map: Optional[dict] = None


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_catalog() -> dict:
    """Return the catalog, loading it from disk on first use."""
    global _catalog
    if _catalog is None:
        _catalog = _load(CATALOG_PATH)
    return _catalog


def get_inventory() -> dict:
    """Return the inventory, loading it from disk on first use."""
    global _inventory
    if _inventory is None:
        _inventory = _load(INVENTORY_PATH)
    return _inventory


def get_symptom_map() -> dict:
    """Return the symptom-to-category map, loading it on first use."""
    global _symptom_map
    if _symptom_map is None:
        _symptom_map = _load(SYMPTOM_MAP_PATH)
    return _symptom_map


def get_medications() -> list[dict]:
    return get_catalog()["medications"]


def medications_in_category(category: str) -> list[dict]:
    """Return all OTC medications belonging to a category."""
    return [
        medication
        for medication in get_medications()
        if medication["category"] == category
        and not medication["requires_prescription"]
    ]


def find_medication(sku: str) -> Optional[dict]:
    """Look up a medication by SKU (case-insensitive)."""
    sku = sku.strip().upper()
    for medication in get_medications():
        if medication["sku"].upper() == sku:
            return medication
    return None


def get_branches() -> list[dict]:
    return get_inventory()["branches"]


def find_branch(branch_id: str) -> Optional[dict]:
    branch_id = branch_id.strip().upper()
    for branch in get_branches():
        if branch["id"].upper() == branch_id:
            return branch
    return None


def get_stock(sku: str) -> dict[str, dict]:
    """Return {branch_id: {units, price}} for one SKU."""
    return get_inventory()["stock"].get(sku.strip().upper(), {})


# --- Orders ------------------------------------------------------------


def load_orders() -> dict:
    """Return the orders file, creating an empty one if missing."""
    if not os.path.exists(ORDERS_PATH):
        return {"next_id": 1, "orders": {}}
    try:
        return _load(ORDERS_PATH)
    except (json.JSONDecodeError, OSError):
        # A corrupted file should not take the whole server down.
        return {"next_id": 1, "orders": {}}


def save_orders(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ORDERS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def orders_lock() -> threading.Lock:
    return _orders_lock


def as_json(payload: Any) -> str:
    """
    Serialize a tool result.

    Tools return text content, and returning JSON keeps the output
    unambiguous for the LLM and readable in the interaction log.
    """
    return json.dumps(payload, indent=2, ensure_ascii=False)
