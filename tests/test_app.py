"""Prueba de la UI con el simulador de Streamlit y un modelo simulado."""

from pathlib import Path

import pytest
import streamlit as st
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

import agente
from tests.test_agente import ModeloFalso, _llamada

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _limpiar_cache():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _parchear_agente(monkeypatch, mensajes):
    real = agente.crear_agente
    guion = iter(mensajes)
    monkeypatch.setattr(
        agente,
        "crear_agente",
        lambda modelo=None, checkpointer=None: real(
            modelo=ModeloFalso(messages=guion), checkpointer=checkpointer
        ),
    )


def test_app_muestra_pasos_y_respuesta_final(monkeypatch):
    _parchear_agente(
        monkeypatch,
        [
            _llamada(
                "proyectar_inflacion",
                {"primer_mes": "2026-11", "rem_mensual_pct": [2.0] * 6, "inflacion_12m_pct": 24.0},
                "x1",
            ),
            AIMessage(content=[{"type": "text", "text": "Proyecté **24 %** a 12 meses."}]),
        ],
    )
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception

    at.chat_input[0].set_value("Proyectá la inflación").run()
    assert not at.exception

    historial = at.session_state["historial"]
    assert historial[0] == {"rol": "user", "texto": "Proyectá la inflación"}
    respuesta = historial[1]
    assert respuesta["texto"] == "Proyecté **24 %** a 12 meses."
    assert [p["tipo"] for p in respuesta["pasos"]] == ["razonamiento", "tool", "resultado"]
    assert any("Proyecté" in m.value for m in at.markdown)


def test_app_nueva_conversacion_limpia_el_historial(monkeypatch):
    _parchear_agente(monkeypatch, [AIMessage(content=[{"type": "text", "text": "Hola."}])])
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("hola").run()
    assert len(at.session_state["historial"]) == 2
    thread_anterior = at.session_state["thread_id"]

    next(b for b in at.sidebar.button if b.label == "Nueva conversación").click().run()
    assert at.session_state["historial"] == []
    assert at.session_state["thread_id"] != thread_anterior
