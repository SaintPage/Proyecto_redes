"""
Capa de acceso a datos para el servidor MCP de farmacia.

Carga el catalogo e inventario ficticios desde archivos JSON y los
mantiene en memoria. Los pedidos se persisten a disco para que su
estado sobreviva entre llamadas a tools (y entre sesiones), que es lo
que le da sentido a `get_order_status`.

Mantener el I/O de archivos aqui deja las funciones de las tools
pequenas y legibles.
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

# Los pedidos se escriben desde llamadas a tools; un lock evita que el
# archivo se corrompa si alguna vez dos llamadas se superponen.
_orders_lock = threading.Lock()

_catalog: Optional[dict] = None
_inventory: Optional[dict] = None
_symptom_map: Optional[dict] = None


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_catalog() -> dict:
    """Retorna el catalogo, cargandolo de disco la primera vez que se usa."""
    global _catalog
    if _catalog is None:
        _catalog = _load(CATALOG_PATH)
    return _catalog


def get_inventory() -> dict:
    """Retorna el inventario, cargandolo de disco la primera vez que se usa."""
    global _inventory
    if _inventory is None:
        _inventory = _load(INVENTORY_PATH)
    return _inventory


def get_symptom_map() -> dict:
    """Retorna el mapa de sintomas a categorias, cargandolo la primera vez."""
    global _symptom_map
    if _symptom_map is None:
        _symptom_map = _load(SYMPTOM_MAP_PATH)
    return _symptom_map


def get_medications() -> list[dict]:
    return get_catalog()["medications"]


def medications_in_category(category: str) -> list[dict]:
    """Retorna todos los medicamentos de venta libre de una categoria."""
    return [
        medication
        for medication in get_medications()
        if medication["category"] == category
        and not medication["requires_prescription"]
    ]


def find_medication(sku: str) -> Optional[dict]:
    """Busca un medicamento por SKU (sin distinguir mayusculas/minusculas)."""
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
    """Retorna {branch_id: {units, price}} para un SKU."""
    return get_inventory()["stock"].get(sku.strip().upper(), {})


# --- Pedidos ------------------------------------------------------------


def load_orders() -> dict:
    """Retorna el archivo de pedidos, creando uno vacio si no existe."""
    if not os.path.exists(ORDERS_PATH):
        return {"next_id": 1, "orders": {}}
    try:
        return _load(ORDERS_PATH)
    except (json.JSONDecodeError, OSError):
        # Un archivo corrupto no debe tumbar todo el servidor.
        return {"next_id": 1, "orders": {}}


def save_orders(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ORDERS_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def orders_lock() -> threading.Lock:
    return _orders_lock


def as_json(payload: Any) -> str:
    """
    Serializa el resultado de una tool.

    Las tools retornan contenido de texto, y retornar JSON mantiene la
    salida sin ambiguedad para el LLM y legible en el log de
    interacciones.
    """
    return json.dumps(payload, indent=2, ensure_ascii=False)