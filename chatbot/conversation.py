"""
Contexto de la sesion (funcionalidad 2).

Mantiene el historial completo de la conversacion. Los LLM no tienen
memoria entre llamadas: cada solicitud a la API debe incluir todos los
turnos anteriores. Esta clase es la que hace posible que el chatbot
entienda preguntas de seguimiento.

Ejemplo del enunciado: si se pregunta "¿Quien fue Alan Turing?" y luego
"¿En que fecha nacio?", la segunda pregunta solo tiene sentido si el
historial de la primera se envia junto con ella.

El historial se guarda como objetos Content de la API de Gemini, que es
el formato que espera generate_content. Ojo: Gemini usa el rol "model"
para los turnos del asistente (no "assistant").
"""

from typing import Any

from google.genai import types


class Conversation:
    """Historial de mensajes de una sesion de chat."""

    def __init__(self) -> None:
        self.contents: list[Any] = []

    def add_user(self, text: str) -> None:
        """Agrega un turno del usuario."""
        self.contents.append(
            types.Content(role="user", parts=[types.Part(text=text)])
        )

    def add_model(self, parts: list) -> None:
        """
        Agrega un turno del modelo.

        `parts` son los bloques que devolvio la API: pueden ser texto,
        llamadas a funciones, o ambos.
        """
        self.contents.append(types.Content(role="model", parts=list(parts)))

    def add_tool_results(self, results: list[tuple[str, dict]]) -> None:
        """
        Agrega los resultados de las herramientas ejecutadas.

        Cada elemento de `results` es (nombre_de_la_tool, respuesta).
        Los resultados de function calling viajan como un turno con rol
        "user" que contiene bloques function_response.
        """
        parts = [
            types.Part.from_function_response(name=name, response=response)
            for name, response in results
        ]
        self.contents.append(types.Content(role="user", parts=parts))

    def reset(self) -> None:
        """Borra el historial completo."""
        self.contents.clear()

    def turn_count(self) -> int:
        """Cuenta cuantos turnos de texto lleva el usuario."""
        return sum(
            1 for c in self.contents
            if c.role == "user" and any(getattr(p, "text", None) for p in c.parts)
        )

    def __len__(self) -> int:
        return len(self.contents)