"""
Pharmacy domain tools (part 2): symptom-based suggestions.

This tool maps a described symptom to categories of over-the-counter
products from the fictional catalog. It is deliberately conservative:

  * If the text matches a red-flag symptom (chest pain, trouble
    breathing, pregnancy, infants, etc.), it returns NO product and
    tells the user to seek professional medical care instead.
  * Otherwise it returns OTC product categories, always paired with a
    reminder to consult the pharmacist.

The server never diagnoses. It suggests catalog categories and knows
when to step back, which is the honest behaviour for a data service.
"""

from typing import Optional

from . import data_store as db
from .registry import tool

DISCLAIMER = (
    "Esta es una sugerencia automatizada basada en un catalogo y no "
    "constituye un diagnostico ni consejo medico. Consulte siempre al "
    "farmaceutico antes de adquirir cualquier medicamento."
)

REFERRAL = (
    "Los sintomas descritos pueden requerir atencion medica. No se "
    "sugieren productos de venta libre. Acuda a un medico o a servicios "
    "de emergencia."
)


def _matches_red_flag(text: str) -> Optional[str]:
    """Return the first red-flag phrase present in `text`, if any."""
    lowered = text.lower()
    for phrase in db.get_symptom_map().get("red_flags", []):
        if phrase in lowered:
            return phrase
    return None


@tool(
    name="suggest_products_for_symptom",
    description=(
        "Given a symptom described in plain language, suggest categories "
        "of over-the-counter products from the catalog. If the symptom "
        "may be serious, it returns a medical referral and no product. "
        "This tool does not diagnose; results are catalog hints only and "
        "always include a reminder to consult the pharmacist."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symptom": {
                "type": "string",
                "description": (
                    "Symptom described by the customer, e.g. 'dolor de "
                    "cabeza' or 'congestion nasal'."
                ),
            },
            "max_products": {
                "type": "integer",
                "description": (
                    "Maximum number of suggested products per category "
                    "(default 3)."
                ),
            },
        },
        "required": ["symptom"],
    },
)
def suggest_products_for_symptom(symptom: str, max_products: int = 3) -> str:
    symptom = (symptom or "").strip()
    if not symptom:
        raise ValueError("symptom must not be empty")
    if max_products < 1 or max_products > 10:
        raise ValueError("max_products must be between 1 and 10")

    # Safety first: a red flag short-circuits any product suggestion.
    red_flag = _matches_red_flag(symptom)
    if red_flag:
        return db.as_json(
            {
                "symptom": symptom,
                "referral": True,
                "matched_red_flag": red_flag,
                "message": REFERRAL,
                "suggestions": [],
            }
        )

    symptom_map = db.get_symptom_map().get("otc_symptoms", {})

    # Match known symptoms as substrings so small phrasing differences
    # ("tengo tos", "tos seca") still map to the same category.
    lowered = symptom.lower()
    matched_categories: list[str] = []
    for known, categories in symptom_map.items():
        if known in lowered:
            for category in categories:
                if category not in matched_categories:
                    matched_categories.append(category)

    if not matched_categories:
        return db.as_json(
            {
                "symptom": symptom,
                "referral": False,
                "message": (
                    "No se encontro una coincidencia en el catalogo para "
                    "ese sintoma. " + DISCLAIMER
                ),
                "suggestions": [],
            }
        )

    suggestions = []
    for category in matched_categories:
        products = db.medications_in_category(category)[:max_products]
        suggestions.append(
            {
                "category": category,
                "products": [
                    {
                        "sku": product["sku"],
                        "name": product["name"],
                        "presentation": product["presentation"],
                    }
                    for product in products
                ],
            }
        )

    return db.as_json(
        {
            "symptom": symptom,
            "referral": False,
            "disclaimer": DISCLAIMER,
            "suggestions": suggestions,
        }
    )
