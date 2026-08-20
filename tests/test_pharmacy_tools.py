"""
Functional tests for the pharmacy tools.

These call the tool handlers directly (no transport involved), which
keeps them fast and makes failures easy to locate. The protocol side is
covered by test_handshake.py.

Run with:  python tests/test_pharmacy_tools.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.tools import pharmacy  # noqa: E402


def check(label: str, condition: bool) -> bool:
    print(f"[{'OK ' if condition else 'FAIL'}] {label}")
    return condition


def main() -> int:
    results = []

    # --- search_medications -------------------------------------------
    found = json.loads(pharmacy.search_medications(query="ibuprofeno"))
    results.append(check("search by active ingredient finds MED-002",
                         any(r["sku"] == "MED-002" for r in found["results"])))

    by_category = json.loads(pharmacy.search_medications(category="antibiotico"))
    results.append(check("category filter returns only antibiotics",
                         all(r["category"] == "antibiotico" for r in by_category["results"])
                         and by_category["count"] > 0))

    otc = json.loads(pharmacy.search_medications(otc_only=True))
    results.append(check("otc_only excludes prescription products",
                         all(not r["requires_prescription"] for r in otc["results"])))

    empty = json.loads(pharmacy.search_medications(query="zzzzz"))
    results.append(check("no matches returns count 0", empty["count"] == 0))

    limited = json.loads(pharmacy.search_medications(limit=3))
    results.append(check("limit caps the result list",
                         limited["count"] == 3 and limited["truncated"] is True))

    try:
        pharmacy.search_medications(category="inventada")
        results.append(check("invalid category raises", False))
    except ValueError:
        results.append(check("invalid category raises", True))

    # --- check_inventory ----------------------------------------------
    inventory = json.loads(pharmacy.check_inventory(sku="MED-002"))
    results.append(check("inventory lists all three branches",
                         len(inventory["availability"]) == 3))

    one = json.loads(pharmacy.check_inventory(sku="MED-001", branch_id="SUC-03"))
    results.append(check("branch filter returns a single branch",
                         len(one["availability"]) == 1
                         and one["availability"][0]["branch_id"] == "SUC-03"))
    results.append(check("out-of-stock branch reports in_stock false",
                         one["availability"][0]["in_stock"] is False))

    lower = json.loads(pharmacy.check_inventory(sku="med-002"))
    results.append(check("SKU lookup is case-insensitive", lower["sku"] == "MED-002"))

    rx = json.loads(pharmacy.check_inventory(sku="MED-011"))
    results.append(check("prescription flag is exposed",
                         rx["requires_prescription"] is True))

    try:
        pharmacy.check_inventory(sku="MED-999")
        results.append(check("unknown SKU raises", False))
    except ValueError:
        results.append(check("unknown SKU raises", True))

    try:
        pharmacy.check_inventory(sku="MED-001", branch_id="SUC-99")
        results.append(check("unknown branch raises", False))
    except ValueError:
        results.append(check("unknown branch raises", True))

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
