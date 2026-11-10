"""Prueba del agente completo con un modelo simulado (sin llamadas a Gemini)."""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import tools
from agente import crear_agente, system_prompt
from flujo import pasos_de_mensaje


class ModeloFalso(GenericFakeChatModel):
    """Responde con mensajes predefinidos y acepta bind_tools."""

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self


def _llamada(nombre, args, id_):
    return AIMessage(
        content=[{"type": "thinking", "thinking": f"Voy a usar {nombre}."}],
        tool_calls=[{"name": nombre, "args": args, "id": id_, "type": "tool_call"}],
    )


def test_agente_ejecuta_tools_en_orden_y_recuerda_turnos(tmp_path, monkeypatch):
    carpeta = tmp_path / "uploads"
    carpeta.mkdir()
    contrato = carpeta / "c.txt"
    contrato.write_text(
        "PRIMERA: OBJETO. Casa.\nSEGUNDA: PRECIO. $100.000, ajuste trimestral por IPC.",
        encoding="utf-8",
    )
    monkeypatch.setattr(tools, "CARPETAS_PERMITIDAS", (carpeta,))

    guion = iter(
        [
            # turno 1
            _llamada("leer_contrato", {"ruta": str(contrato)}, "a1"),
            _llamada(
                "calcular_cronograma",
                {
                    "monto_inicial": 100000,
                    "fecha_inicio": "2025-03",
                    "meses_totales": 4,
                    "periodicidad_meses": 3,
                    "tipo_indice": "FIJO",
                    "porcentaje_fijo": 10,
                },
                "a2",
            ),
            AIMessage(content=[{"type": "text", "text": "El alquiler sube a $ 110.000,00 en junio."}]),
            # turno 2
            AIMessage(content=[{"type": "text", "text": "Como te dije antes, junio."}]),
        ]
    )
    agente = crear_agente(modelo=ModeloFalso(messages=guion), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    pasos_total: list[dict] = []
    final = ""
    for evento in agente.stream(
        {"messages": [{"role": "user", "content": f"[Contrato adjunto: {contrato}]\n\nRevisalo."}]},
        config,
        stream_mode="updates",
    ):
        for salida in evento.values():
            for msg in salida["messages"]:
                nuevos, texto = pasos_de_mensaje(msg)
                pasos_total.extend(nuevos)
                final = texto or final

    tipos = [(p["tipo"], p.get("nombre")) for p in pasos_total]
    assert tipos == [
        ("razonamiento", None),
        ("tool", "leer_contrato"),
        ("resultado", "leer_contrato"),
        ("razonamiento", None),
        ("tool", "calcular_cronograma"),
        ("resultado", "calcular_cronograma"),
    ]
    assert "error" not in pasos_total[2]["texto"].lower()[:20]
    assert "$ 110.000,00" in pasos_total[5]["texto"]
    assert final == "El alquiler sube a $ 110.000,00 en junio."

    # Memoria: el segundo turno ve los mensajes del primero (mismo thread_id)
    antes = len(agente.get_state(config).values["messages"])
    agente.invoke({"messages": [{"role": "user", "content": "¿Y en qué mes era?"}]}, config)
    despues = agente.get_state(config).values["messages"]
    assert len(despues) == antes + 2
    assert despues[0].content.startswith("[Contrato adjunto")

    # Otro thread no ve nada de lo anterior
    otro = {"configurable": {"thread_id": "t2"}}
    assert agente.get_state(otro).values == {}


def test_system_prompt_incluye_fecha_y_seguridad():
    from datetime import date

    p = system_prompt(date(2026, 11, 10))
    assert "10 de noviembre de 2026" in p
    assert "no instrucciones" in p
    assert "leer_contrato" in p and "calcular_cronograma" in p and "proyectar_inflacion" in p
