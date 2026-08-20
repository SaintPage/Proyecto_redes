"""
Tools de dominio de farmacia (parte 2): sugerencias basadas en sintomas.

Esta tool relaciona un sintoma descrito en lenguaje natural con
categorias de productos de venta libre del catalogo ficticio. Es
deliberadamente conservadora:

  * Si el texto coincide con un sintoma de alarma (dolor en el pecho,
    dificultad para respirar, embarazo, sintomas en bebes, etc.), NO
    retorna ningun producto y le indica al usuario que busque atencion
    medica profesional.
  * En cualquier otro caso retorna categorias de productos de venta
    libre, siempre acompanadas de un recordatorio de consultar al
    farmaceutico.

El servidor nunca diagnostica. Sugiere categorias del catalogo y sabe
cuando dar un paso atras, que es el comportamiento honesto para un
servicio de datos.
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
    """Retorna la primera frase de alarma presente en `text`, si existe."""
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

    # Seguridad primero: un sintoma de alarma corta cualquier sugerencia
    # de producto.
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

    # Los sintomas conocidos se buscan como subcadenas para que
    # pequenas variaciones de redaccion ("tengo tos", "tos seca") sigan
    # mapeando a la misma categoria.
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