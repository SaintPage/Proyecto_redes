"""
Paquete de tools.

Importar un modulo de tool aqui es lo que registra sus tools, para que
la capa de protocolo nunca necesite saber cuales existen.
"""

from . import pharmacy           # noqa: F401  search_medications, check_inventory
from . import pharmacy_symptoms  # noqa: F401  suggest_products_for_symptom
from . import pharmacy_orders    # noqa: F401  create_order, get_order_status
from .registry import get_tool, list_tools, tool, validate_arguments  # noqa: F401