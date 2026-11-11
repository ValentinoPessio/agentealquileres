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

st.set_page_config(
    page_title="Revisor de contratos de alquiler", page_icon=":material/home_work:", layout="wide"
)

CONTRATOS_EJEMPLO = Path(__file__).resolve().parent / "data" / "contratos_ejemplo"

# Etiquetas legibles para el estado del agente mientras trabaja.
ETAPAS = {
    "leer_contrato": "Leyendo el contrato",
    "buscar_normativa": "Consultando la normativa",
    "consultar_indices": "Consultando índices oficiales",
    "proyectar_inflacion": "Proyectando la inflación",
    "calcular_cronograma": "Calculando el cronograma de alquileres",
}

SUGERENCIAS = [
    ("Revisar un contrato", "Revisá este contrato y marcame las cláusulas problemáticas."),
    ("Proyectar el alquiler", "Mostrame cómo se actualiza el alquiler en los próximos 12 meses."),
    ("Rescisión anticipada", "¿Puedo rescindir antes de tiempo y cuánto pagaría?"),
]

ESTILOS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Lora:wght@500;600&display=swap');
:root { --petroleo:#1F3A5F; --laton:#A67C37; --papel:#F7F5F0; --borde:#D9D3C5; }
h1, h2, h3, .encabezado h1 { font-family: 'Lora', Georgia, 'Times New Roman', serif !important; color: var(--petroleo); letter-spacing: 0; }
[data-testid="stSidebar"] { border-right: 1px solid var(--borde); }
[data-testid="stSidebar"] h2 { font-size: 1.05rem; text-transform: uppercase; letter-spacing: .08em; color: var(--laton); }
.encabezado { display:flex; align-items:center; gap:.9rem; padding-bottom:.6rem; border-bottom:2px solid var(--laton); margin-bottom:.4rem; }
.encabezado h1 { margin:0; padding:0; font-size:1.9rem; line-height:1.2; }
.encabezado svg { flex:none; }
.aviso { color:#5B6670; font-size:.88rem; margin:.2rem 0 1rem 0; }
.contrato-activo { background:#fff; border:1px solid var(--borde); border-left:4px solid var(--laton); border-radius:6px; padding:.55rem .75rem; font-size:.9rem; }
.contrato-activo small { color:#5B6670; display:block; }
[data-testid="stChatMessage"] { background:#fff; border:1px solid var(--borde); border-radius:8px; }
[data-testid="stMarkdownContainer"] table { border-collapse:collapse; width:100%; font-size:.92rem; }
[data-testid="stMarkdownContainer"] th { background:var(--petroleo); color:#fff; padding:.45rem .6rem; border:1px solid var(--petroleo); }
[data-testid="stMarkdownContainer"] td { padding:.4rem .6rem; border:1px solid var(--borde); }
[data-testid="stMarkdownContainer"] tbody tr:nth-child(even) td { background:#F4F1EA; }
.stButton > button { border-radius:6px; border:1px solid var(--petroleo); }
</style>
"""

ICONO = (
    '<svg width="44" height="44" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<path d="M6 22 24 7l18 15" stroke="#1F3A5F" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
    '<path d="M11 20v20h26V20" stroke="#1F3A5F" stroke-width="3" stroke-linejoin="round"/>'
    '<circle cx="24" cy="27" r="3.5" stroke="#A67C37" stroke-width="2.5"/>'
    '<path d="M24 30.5V37m0-3h3" stroke="#A67C37" stroke-width="2.5" stroke-linecap="round"/></svg>'
)


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
    st.session_state.setdefault("uploader_n", 0)


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
        st.markdown(":material/psychology: **Razonamiento**")
        st.caption(paso["texto"])
    elif tipo == "comentario":
        st.markdown(paso["texto"])
    elif tipo == "tool":
        st.markdown(f":material/build: **Tool invocada:** `{paso['nombre']}`")
        st.json(paso["args"], expanded=False)
    elif tipo == "resultado":
        st.markdown(f":material/task_alt: **Resultado de** `{paso['nombre']}`")
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

st.markdown(ESTILOS, unsafe_allow_html=True)
st.markdown(
    f'<div class="encabezado">{ICONO}<h1>Revisor de contratos de alquiler</h1></div>'
    '<p class="aviso">Subí un contrato y consultá por sus cláusulas o por cómo se actualiza el alquiler. '
    "Es una ayuda para entender el contrato: no reemplaza a un abogado.</p>",
    unsafe_allow_html=True,
)

def _nombre_visible(ruta: str) -> str:
    nombre = Path(ruta).name
    return re.sub(r"^[0-9a-f]{8}_", "", nombre)


def _nueva_conversacion() -> None:
    st.session_state.uploader_n += 1  # vacía el cuadro de carga
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.historial = []
    st.session_state.adjunto = None
    st.session_state.adjunto_anunciado = True
    st.session_state.ultimo_archivo = None


def _selector_contrato() -> None:
    """Carga de contrato: archivo propio o uno de los ejemplos."""
    archivo = st.file_uploader(
        "Arrastrá tu contrato o elegilo desde tu computadora (PDF o TXT)",
        type=["pdf", "txt"],
        key=f"uploader_{st.session_state.uploader_n}",
    )
    if archivo is not None:
        clave = f"{archivo.name}:{archivo.size}"
        if clave != st.session_state.ultimo_archivo:
            st.session_state.adjunto = _guardar_adjunto(archivo)
            st.session_state.adjunto_anunciado = False
            st.session_state.ultimo_archivo = clave

    ejemplos = sorted(p.name for p in CONTRATOS_EJEMPLO.glob("*") if p.suffix in (".txt", ".pdf"))
    if ejemplos:
        col_ej, col_btn = st.columns([3, 1], vertical_alignment="bottom")
        elegido = col_ej.selectbox(
            "...o probá con un contrato de ejemplo", ejemplos, index=None, placeholder="Elegir ejemplo"
        )
        if col_btn.button("Cargar", disabled=elegido is None, use_container_width=True):
            st.session_state.adjunto = (CONTRATOS_EJEMPLO / elegido).relative_to(UPLOADS.parent.parent).as_posix()
            st.session_state.adjunto_anunciado = False
            st.session_state.ultimo_archivo = None
            st.rerun()


def _tarjeta_contrato() -> None:
    if st.session_state.adjunto:
        st.markdown(
            f'<div class="contrato-activo"><small>Contrato activo</small>'
            f"{_nombre_visible(st.session_state.adjunto)}</div>",
            unsafe_allow_html=True,
        )


with st.sidebar:
    st.header("Conversación")
    _tarjeta_contrato()
    if st.button("Nueva conversación", use_container_width=True):
        _nueva_conversacion()
        st.rerun()
    st.caption("Fuentes: CCyC, DNU 70/2023, Ley 24.240, INDEC y BCRA.")

# Contrato: caja central antes de empezar; después, un panel plegable.
if st.session_state.historial:
    titulo = (
        f"Contrato: {_nombre_visible(st.session_state.adjunto)}"
        if st.session_state.adjunto
        else "Cargar un contrato"
    )
    with st.expander(titulo, expanded=False):
        _selector_contrato()
zona_contrato = st.empty()
if not st.session_state.historial:
    with zona_contrato.container():
        _, centro, _ = st.columns([1, 6, 1])
        with centro:
            with st.container(border=True):
                st.markdown("#### Cargá tu contrato")
                _selector_contrato()
                _tarjeta_contrato()

try:
    agente = _agente()
except ConfigError as exc:
    st.error(f"Configuración incompleta: {exc}")
    st.stop()

AVATARES = {"user": ":material/person:", "assistant": ":material/home_work:"}

# Historial
for item in st.session_state.historial:
    with st.chat_message(item["rol"], avatar=AVATARES[item["rol"]]):
        if item["rol"] == "assistant" and item.get("pasos"):
            with st.expander("Pasos del agente", expanded=False):
                mostrar_pasos(item["pasos"])
        st.markdown(item["texto"])

# Entrada del usuario
zona_sugerencias = st.empty()
if not st.session_state.historial:
    with zona_sugerencias.container():
        st.markdown("##### O empezá con una consulta rápida")
        columnas = st.columns(len(SUGERENCIAS))
        for col, (titulo, texto) in zip(columnas, SUGERENCIAS):
            if col.button(titulo, help=texto, use_container_width=True):
                st.session_state.consulta_pendiente = texto
                st.rerun()

consulta = st.chat_input("Escribí tu consulta...") or st.session_state.pop("consulta_pendiente", None)
if consulta:
    zona_sugerencias.empty()
    zona_contrato.empty()
    st.session_state.historial.append({"rol": "user", "texto": consulta})
    with st.chat_message("user", avatar=AVATARES["user"]):
        st.markdown(consulta)

    contenido = consulta
    if st.session_state.adjunto and not st.session_state.adjunto_anunciado:
        contenido = f"[Contrato adjunto: {st.session_state.adjunto}]\n\n{consulta}"
        st.session_state.adjunto_anunciado = True

    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    pasos: list[dict] = []
    texto_final = ""

    with st.chat_message("assistant", avatar=AVATARES["assistant"]):
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
                                if paso["tipo"] == "tool":
                                    estado.update(label=f"{ETAPAS.get(paso['nombre'], 'Trabajando')}...")
                                mostrar_paso(paso)  # se ve mientras el agente trabaja
                            pasos.extend(nuevos)
                            if final:
                                texto_final = final
                herramientas = sum(1 for p in pasos if p["tipo"] == "tool")
                estado.update(label=f"Listo · {herramientas} {'tool usada' if herramientas == 1 else 'tools usadas'}", state="complete", expanded=False)
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            texto_final = (
                f"Falló la llamada al modelo: `{type(exc).__name__}`. "
                "Si es un 429 con \"RESOURCE_EXHAUSTED\", se agotó la cuota gratuita del modelo "
                "(se renueva a diario): probá con otro modelo en GEMINI_FALLBACK_MODELS. "
                "Si es un 503, el servicio está saturado: esperá un momento y reintentá."
            )
            st.error(f"{type(exc).__name__}: {exc}")

        if texto_final:
            st.markdown(texto_final)
        else:
            st.warning("El agente no devolvió una respuesta final.")

    st.session_state.historial.append(
        {"rol": "assistant", "texto": texto_final or "(sin respuesta)", "pasos": pasos}
    )
