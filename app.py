"""UI web (Streamlit) del agente revisor de contratos de alquiler.

Ejecutar:  streamlit run app.py
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import streamlit as st
from langgraph.checkpoint.memory import InMemorySaver

from agente import crear_agente
from flujo import pasos_de_mensaje
from model import ConfigError

UPLOADS = Path(__file__).resolve().parent / "outputs" / "uploads"

st.set_page_config(page_title="Revisor de contratos de alquiler", layout="wide")


# ---------------------------------------------------------------------------
# Recursos compartidos
# ---------------------------------------------------------------------------

@st.cache_resource
def _checkpointer() -> InMemorySaver:
    # La memoria vive mientras corra el servidor; cada conversación usa su thread_id.
    return InMemorySaver()


@st.cache_resource
def _agente():
    return crear_agente(checkpointer=_checkpointer())


def _estado_inicial() -> None:
    st.session_state.setdefault("thread_id", str(uuid.uuid4()))
    st.session_state.setdefault("historial", [])
    st.session_state.setdefault("adjunto", None)  # ruta relativa del contrato subido
    st.session_state.setdefault("adjunto_anunciado", True)
    st.session_state.setdefault("ultimo_archivo", None)


def _guardar_adjunto(archivo) -> str:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^A-Za-z0-9._-]", "_", Path(archivo.name).name)
    destino = UPLOADS / f"{uuid.uuid4().hex[:8]}_{nombre}"
    destino.write_bytes(archivo.getvalue())
    return destino.relative_to(UPLOADS.parent.parent).as_posix()


# ---------------------------------------------------------------------------
# Render de pasos del agente
# ---------------------------------------------------------------------------

def mostrar_paso(paso: dict) -> None:
    tipo = paso["tipo"]
    if tipo == "razonamiento":
        st.markdown("**Razonamiento**")
        st.caption(paso["texto"])
    elif tipo == "comentario":
        st.markdown(paso["texto"])
    elif tipo == "tool":
        st.markdown(f"**Tool invocada:** `{paso['nombre']}`")
        st.json(paso["args"], expanded=False)
    elif tipo == "resultado":
        st.markdown(f"**Resultado de** `{paso['nombre']}`")
        if paso["error"]:
            st.error(paso["texto"])
        else:
            st.code(paso["texto"], language=None)


def mostrar_pasos(pasos: list[dict]) -> None:
    for paso in pasos:
        mostrar_paso(paso)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_estado_inicial()

st.title("Revisor de contratos de alquiler")
st.caption(
    "Subí un contrato y consultá por sus cláusulas o por cómo se actualiza el alquiler. "
    "Es una ayuda para entender el contrato: no reemplaza a un abogado."
)

with st.sidebar:
    st.header("Contrato")
    archivo = st.file_uploader("Contrato (PDF o TXT)", type=["pdf", "txt"])
    if archivo is not None:
        clave = f"{archivo.name}:{archivo.size}"
        if clave != st.session_state.ultimo_archivo:
            st.session_state.adjunto = _guardar_adjunto(archivo)
            st.session_state.adjunto_anunciado = False
            st.session_state.ultimo_archivo = clave
        st.success(f"Cargado: {archivo.name}")

    if st.button("Nueva conversación"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.historial = []
        st.session_state.adjunto = None
        st.session_state.adjunto_anunciado = True
        st.session_state.ultimo_archivo = None
        st.rerun()

try:
    agente = _agente()
except ConfigError as exc:
    st.error(f"Configuración incompleta: {exc}")
    st.stop()

# Historial
for item in st.session_state.historial:
    with st.chat_message(item["rol"]):
        if item["rol"] == "assistant" and item.get("pasos"):
            with st.expander("Pasos del agente", expanded=False):
                mostrar_pasos(item["pasos"])
        st.markdown(item["texto"])

# Entrada del usuario
consulta = st.chat_input("Escribí tu consulta...")
if consulta:
    st.session_state.historial.append({"rol": "user", "texto": consulta})
    with st.chat_message("user"):
        st.markdown(consulta)

    contenido = consulta
    if st.session_state.adjunto and not st.session_state.adjunto_anunciado:
        contenido = f"[Contrato adjunto: {st.session_state.adjunto}]\n\n{consulta}"
        st.session_state.adjunto_anunciado = True

    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    pasos: list[dict] = []
    texto_final = ""

    with st.chat_message("assistant"):
        try:
            with st.status("El agente está trabajando...", expanded=True) as estado:
                for evento in agente.stream(
                    {"messages": [{"role": "user", "content": contenido}]},
                    config,
                    stream_mode="updates",
                ):
                    for salida in evento.values():
                        mensajes = (salida or {}).get("messages", [])
                        if not isinstance(mensajes, list):
                            mensajes = [mensajes]
                        for msg in mensajes:
                            nuevos, final = pasos_de_mensaje(msg)
                            for paso in nuevos:
                                mostrar_paso(paso)  # se ve mientras el agente trabaja
                            pasos.extend(nuevos)
                            if final:
                                texto_final = final
                estado.update(label="Listo", state="complete", expanded=False)
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            texto_final = (
                f"Falló la llamada al modelo: `{type(exc).__name__}`. "
                "Si es un 429 o 503, el servicio está saturado: esperá un momento y reintentá."
            )
            st.error(f"{type(exc).__name__}: {exc}")

        if texto_final:
            st.markdown(texto_final)
        else:
            st.warning("El agente no devolvió una respuesta final.")

    st.session_state.historial.append(
        {"rol": "assistant", "texto": texto_final or "(sin respuesta)", "pasos": pasos}
    )
