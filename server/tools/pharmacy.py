"""
Tools de dominio de farmacia (parte 1): busqueda en catalogo y consulta
de inventario.

Caso de uso de industria: una cadena de farmacias expone su catalogo,
existencias y sistema de pedidos a un chatbot para que los clientes
puedan buscar productos, revisar disponibilidad por sucursal y hacer
pedidos.

Todos los datos son ficticios y viven bajo data/. Nada aqui da consejo
medico: las tools describen productos, no diagnostican.
"""

from typing import Optional

from . import data_store as db
from .registry import tool

CATEGORIES = [
    "analgesico",
    "antiinflamatorio",
    "antigripal",
    "antialergico",
    "gastrointestinal",
    "dermatologico",
    "antibiotico",
    "vitaminas",
    "primeros_auxilios",
]


@tool(
    name="search_medications",
    description=(
        "Search the pharmacy catalog by product name, active ingredient "
        "or category. Returns matching products with their SKU, "
        "presentation and whether a prescription is required. Use this "
        "to find the SKU of a product before checking stock or ordering."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Free text matched against the product name and "
                    "active ingredient, e.g. 'ibuprofeno'."
                ),
            },
            "category": {
                "type": "string",
                "enum": CATEGORIES,
                "description": "Restrict results to one product category.",
            },
            "otc_only": {
                "type": "boolean",
                "description": (
                    "If true, return only products that do not require a "
                    "prescription."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default 10).",
            },
        },
        "required": [],
    },
)
def search_medications(
    query: Optional[str] = None,
    category: Optional[str] = None,
    otc_only: bool = False,
    limit: int = 10,
) -> str:
    if category and category not in CATEGORIES:
        raise ValueError(
            f"Unknown category '{category}'. Valid values: {', '.join(CATEGORIES)}"
        )
    if limit < 1 or limit > 50:
        raise ValueError("limit must be between 1 and 50")

    needle = (query or "").strip().lower()
    results = []

    for medication in db.get_medications():
        if category and medication["category"] != category:
            continue
        if otc_only and medication["requires_prescription"]:
            continue
        if needle:
            haystack = (
                f"{medication['name']} {medication['active_ingredient']} "
                f"{medication['category']}"
            ).lower()
            if needle not in haystack:
                continue
        results.append(
            {
                "sku": medication["sku"],
                "name": medication["name"],
                "active_ingredient": medication["active_ingredient"],
                "category": medication["category"],
                "presentation": medication["presentation"],
                "requires_prescription": medication["requires_prescription"],
            }
        )

    truncated = len(results) > limit
    return db.as_json(
        {
            "count": min(len(results), limit),
            "truncated": truncated,
            "results": results[:limit],
        }
    )


@tool(
    name="check_inventory",
    description=(
        "Check availability and price of a product across the pharmacy "
        "branches. Requires the product SKU, which can be obtained with "
        "search_medications. Optionally filter by a single branch."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "sku": {
                "type": "string",
                "description": "Product SKU, e.g. 'MED-002'.",
            },
            "branch_id": {
                "type": "string",
                "description": (
                    "Optional branch identifier, e.g. 'SUC-01'. If "
                    "omitted, all branches are returned."
                ),
            },
        },
        "required": ["sku"],
    },
)
def check_inventory(sku: str, branch_id: Optional[str] = None) -> str:
    medication = db.find_medication(sku)
    if medication is None:
        raise ValueError(f"Unknown SKU '{sku}'. Use search_medications to find it.")

    stock = db.get_stock(sku)
    currency = db.get_inventory().get("currency", "GTQ")

    if branch_id:
        branch = db.find_branch(branch_id)
        if branch is None:
            valid = ", ".join(b["id"] for b in db.get_branches())
            raise ValueError(f"Unknown branch '{branch_id}'. Valid branches: {valid}")
        wanted = [branch]
    else:
        wanted = db.get_branches()

    availability = []
    for branch in wanted:
        entry = stock.get(branch["id"], {"units": 0, "price": None})
        availability.append(
            {
                "branch_id": branch["id"],
                "branch_name": branch["name"],
                "address": branch["address"],
                "hours": branch["hours"],
                "units": entry["units"],
                "in_stock": entry["units"] > 0,
                "price": entry["price"],
            }
        )

    return db.as_json(
        {
            "sku": medication["sku"],
            "name": medication["name"],
            "requires_prescription": medication["requires_prescription"],
            "currency": currency,
            "total_units": sum(item["units"] for item in availability),
            "availability": availability,
        }
    )