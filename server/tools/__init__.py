"""
Tool package.

Importing a tool module here is what registers its tools, so the
protocol layer never needs to know which tools exist.
"""

from . import pharmacy  # noqa: F401  (registers the pharmacy tools)
from .registry import get_tool, list_tools, tool, validate_arguments  # noqa: F401
