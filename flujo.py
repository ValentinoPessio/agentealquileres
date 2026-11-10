"""Convierte los mensajes que produce el agente en "pasos" mostrables en la UI.

No depende de Streamlit, así se puede testear sin interfaz.

Tipos de paso:
  {"tipo": "razonamiento", "texto": str}
  {"tipo": "comentario",   "texto": str}         texto del modelo junto a una tool call
  {"tipo": "tool",         "nombre": str, "args": dict}
  {"tipo": "resultado",    "nombre": str, "texto": str, "error": bool}
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

LIMITE_RESULTADO = 800  # caracteres que se muestran del resultado de una tool


def resumir(texto: str, limite: int = LIMITE_RESULTADO) -> str:
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    return texto[:limite].rstrip() + f"... [{len(texto) - limite} caracteres más]"


def _texto_de_bloques(contenido) -> str:
    """Une los bloques de texto de un contenido que puede ser str o lista."""
    if isinstance(contenido, str):
        return contenido
    partes: list[str] = []
    for bloque in contenido or []:
        if isinstance(bloque, str):
            partes.append(bloque)
        elif isinstance(bloque, dict) and bloque.get("type") == "text":
            partes.append(str(bloque.get("text", "")))
    return "".join(partes)


def extraer_partes(msg: AIMessage) -> tuple[str, str]:
    """Devuelve (razonamiento, texto) de un AIMessage.

    Soporta los bloques de Gemini ('thinking') y los estándar de LangChain
    ('reasoning'). Si el modelo no expone razonamiento, devuelve ''.
    """
    razonamiento: list[str] = []
    texto: list[str] = []
    contenido = msg.content

    if isinstance(contenido, str):
        return "", contenido

    for bloque in contenido or []:
        if isinstance(bloque, str):
            texto.append(bloque)
            continue
        if not isinstance(bloque, dict):
            continue
        tipo = bloque.get("type")
        if tipo in ("thinking", "reasoning"):
            razonamiento.append(str(bloque.get("thinking") or bloque.get("reasoning") or ""))
        elif tipo == "text":
            texto.append(str(bloque.get("text", "")))

    return "\n".join(r for r in razonamiento if r).strip(), "".join(texto).strip()


def pasos_de_mensaje(msg) -> tuple[list[dict], str]:
    """Devuelve (pasos, texto_final) para un mensaje del agente.

    `texto_final` solo se completa con la respuesta definitiva (un AIMessage sin
    tool calls); en el resto de los casos es ''.
    """
    if isinstance(msg, AIMessage):
        razonamiento, texto = extraer_partes(msg)
        pasos: list[dict] = []
        if razonamiento:
            pasos.append({"tipo": "razonamiento", "texto": razonamiento})
        llamadas = msg.tool_calls or []
        if llamadas:
            if texto:
                pasos.append({"tipo": "comentario", "texto": texto})
            for c in llamadas:
                pasos.append({"tipo": "tool", "nombre": c["name"], "args": c["args"]})
            return pasos, ""
        return pasos, texto

    if isinstance(msg, ToolMessage):
        return [
            {
                "tipo": "resultado",
                "nombre": msg.name or "tool",
                "texto": resumir(_texto_de_bloques(msg.content)),
                "error": getattr(msg, "status", None) == "error",
            }
        ], ""

    return [], ""
