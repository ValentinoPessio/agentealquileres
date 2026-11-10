"""Prueba rápida del proveedor de LLM.

Verifica tres cosas que pide la consigna del integrador:
  1. que el modelo hace tool calling,
  2. si devuelve bloques de razonamiento,
  3. que la memoria de corto plazo (checkpointer) funciona entre turnos.

Uso (desde la raíz del repo, con el .env completo):
    python scripts/probar_modelo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from model import ConfigError, get_model


@tool
def sumar(a: float, b: float) -> float:
    """Suma dos números y devuelve el resultado."""
    return a + b


def describir(mensajes) -> None:
    """Imprime tool calls y tipos de bloques de contenido de cada mensaje."""
    for m in mensajes:
        tipo = m.__class__.__name__
        llamadas = getattr(m, "tool_calls", None) or []
        for c in llamadas:
            print(f"  [{tipo}] tool_call: {c['name']}({c['args']})")
        contenido = m.content
        if isinstance(contenido, list):
            tipos = [b.get("type", "?") if isinstance(b, dict) else "str" for b in contenido]
            print(f"  [{tipo}] bloques: {tipos}")
        elif contenido:
            print(f"  [{tipo}] texto: {str(contenido)[:150]}")


def main() -> int:
    try:
        modelo = get_model()
    except ConfigError as exc:
        print(f"Error de configuración: {exc}")
        return 1

    agente = create_agent(
        model=modelo,
        tools=[sumar],
        system_prompt="Sos un asistente. Para sumar usá siempre la tool `sumar`.",
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "prueba-1"}}

    try:
        print("\n--- Turno 1: ¿cuánto es 2 + 3? ---")
        r1 = agente.invoke({"messages": [("user", "¿Cuánto es 2 + 3?")]}, config)
        describir(r1["messages"])

        print("\n--- Turno 2 (depende del anterior): multiplicá ese resultado por 4 ---")
        r2 = agente.invoke(
            {"messages": [("user", "Ahora multiplicá ese resultado por 4 (hacelo vos, sin tool).")]},
            config,
        )
        describir(r2["messages"][-2:])
        print(f"\nRespuesta final: {r2['messages'][-1].text if hasattr(r2['messages'][-1], 'text') else r2['messages'][-1].content}")
    except Exception as exc:  # noqa: BLE001 - es un script de diagnóstico
        print(f"\nFalló la llamada al modelo: {type(exc).__name__}: {exc}")
        print("Si es un 429, el tier gratuito alcanzó su límite: esperen y reintenten.")
        return 2

    print(
        "\nChecklist:"
        "\n  - ¿Hubo un tool_call a `sumar` en el turno 1?  (tool calling)"
        "\n  - ¿Aparecen bloques de tipo 'thinking' o 'reasoning'?  (razonamiento)"
        "\n  - ¿La respuesta final del turno 2 menciona 20?  (memoria)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
