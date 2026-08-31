"""
Lista los modelos de Gemini disponibles para tu API key.

Util para saber que valor poner en GEMINI_MODEL si el modelo por
defecto (gemini-2.5-flash) no esta disponible para tu llave, o si
queres usar uno mas nuevo.

Uso:
    python scripts/list_models.py
"""

import os
import sys

try:
    from google import genai
except ImportError:
    print("Falta el paquete 'google-genai'. Instalalo con:\n"
          "    pip install google-genai", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Falta la variable de entorno GEMINI_API_KEY.", file=sys.stderr)
        return 1

    client = genai.Client(api_key=api_key)

    print("Modelos que soportan generacion de contenido:\n")
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue
        # El nombre viene como "models/gemini-x"; se muestra limpio
        # porque asi es como se pasa en GEMINI_MODEL.
        name = model.name.removeprefix("models/")
        display = getattr(model, "display_name", "") or ""
        print(f"  {name:<40} {display}")

    print("\nPara usar uno distinto al de por defecto:")
    print('    PowerShell:  $env:GEMINI_MODEL="nombre-del-modelo"')
    print('    Git Bash:    export GEMINI_MODEL="nombre-del-modelo"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
