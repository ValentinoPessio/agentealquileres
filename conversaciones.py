"""Persistencia de las conversaciones en SQLite, en un archivo del disco local.

Dos cosas conviven en el mismo archivo (data/conversaciones.sqlite):
  * Los checkpoints del agente (LangGraph `SqliteSaver`): guardan todos los mensajes de
    cada conversación, y por eso el agente puede retomar una conversación después de
    reiniciar la app.
  * Una tabla propia, `conversaciones`, con el título y el contrato de cada una, para
    listarlas y retomarlas desde la UI.

Se puede cambiar la ubicación con la variable de entorno CONVERSACIONES_DB.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from flujo import pasos_de_mensaje

BASE = Path(__file__).resolve().parent
RUTA_DB = BASE / "data" / "conversaciones.sqlite"

RE_ADJUNTO = re.compile(r"^\[Contrato adjunto: [^\]]*\]\s*", re.MULTILINE)


def ruta_db() -> Path:
    return Path(os.getenv("CONVERSACIONES_DB") or RUTA_DB)


class Almacen:
    """Checkpointer persistente + listado de conversaciones."""

    def __init__(self, ruta: str | Path | None = None):
        self.ruta = Path(ruta) if ruta else ruta_db()
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: Streamlit atiende cada interacción en un hilo distinto.
        self._conn_checkpoints = sqlite3.connect(self.ruta, check_same_thread=False, timeout=15)
        self._conn_checkpoints.execute("PRAGMA journal_mode=WAL")
        self.checkpointer = SqliteSaver(self._conn_checkpoints)
        self._conn = sqlite3.connect(self.ruta, check_same_thread=False, timeout=15)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS conversaciones ("
            " thread_id TEXT PRIMARY KEY, titulo TEXT NOT NULL, contrato_ruta TEXT,"
            " creada TEXT NOT NULL, actualizada TEXT NOT NULL)"
        )
        self._conn.commit()

    def registrar(self, thread_id: str, titulo: str, contrato_ruta: str | None) -> None:
        """Crea la conversación (con su título) o actualiza el contrato y la fecha."""
        ahora = datetime.now().isoformat(timespec="seconds")
        titulo = " ".join(titulo.split())[:70] or "Conversación"
        self._conn.execute(
            "INSERT INTO conversaciones (thread_id, titulo, contrato_ruta, creada, actualizada)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(thread_id) DO UPDATE SET"
            "  contrato_ruta = excluded.contrato_ruta, actualizada = excluded.actualizada",
            (thread_id, titulo, contrato_ruta, ahora, ahora),
        )
        self._conn.commit()

    def listar(self, limite: int = 12) -> list[dict]:
        filas = self._conn.execute(
            "SELECT thread_id, titulo, contrato_ruta, actualizada FROM conversaciones"
            " ORDER BY actualizada DESC LIMIT ?",
            (limite,),
        ).fetchall()
        return [
            {"thread_id": t, "titulo": ti, "contrato_ruta": c, "actualizada": a}
            for t, ti, c, a in filas
        ]

    def obtener(self, thread_id: str) -> dict | None:
        fila = self._conn.execute(
            "SELECT thread_id, titulo, contrato_ruta, actualizada FROM conversaciones WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if not fila:
            return None
        return dict(zip(("thread_id", "titulo", "contrato_ruta", "actualizada"), fila))

    def cerrar(self) -> None:
        self._conn.close()
        self._conn_checkpoints.close()


def historial_desde_mensajes(mensajes: list) -> list[dict]:
    """Reconstruye lo que muestra la UI (mensajes y pasos) desde los mensajes guardados."""
    items: list[dict] = []
    pasos: list[dict] = []
    for msg in mensajes:
        if isinstance(msg, HumanMessage):
            texto = msg.content if isinstance(msg.content, str) else str(msg.content)
            items.append({"rol": "user", "texto": RE_ADJUNTO.sub("", texto).strip()})
            pasos = []
            continue
        nuevos, final = pasos_de_mensaje(msg)
        pasos.extend(nuevos)
        if final:
            items.append({"rol": "assistant", "texto": final, "pasos": pasos})
            pasos = []
    if pasos:  # la ejecución se cortó antes de la respuesta final
        items.append({"rol": "assistant", "texto": "(sin respuesta)", "pasos": pasos})
    return items
