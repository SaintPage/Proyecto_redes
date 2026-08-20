"""
Tool package.

Importing a tool module here is what registers its tools. To add the
domain tools, create the module and import it below.
"""

from . import example  # noqa: F401  (temporary placeholder tool)
from .registry import get_tool, list_tools, tool, validate_arguments  # noqa: F401