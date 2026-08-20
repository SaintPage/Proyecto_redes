"""
Tool package.

Importing a tool module here is what registers its tools, so the
protocol layer never needs to know which tools exist.
"""

from . import pharmacy          # noqa: F401  search_medications, check_inventory
from . import pharmacy_symptoms  # noqa: F401  suggest_products_for_symptom
from . import pharmacy_orders    # noqa: F401  create_order, get_order_status
from .registry import get_tool, list_tools, tool, validate_arguments  # noqa: F401
