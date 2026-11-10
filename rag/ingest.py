"""Ingesta de la normativa: un fragmento por artículo, indexado en ChromaDB.

Uso:  python -m rag.ingest            (reconstruye el índice desde data/normativa/*.md)

Cada archivo .md tiene un encabezado con "Norma:" y "Fuente:" y luego bloques
"## Art. N" con el texto literal. Un artículo = un fragmento, para poder citarlo.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CARPETA_NORMATIVA = BASE / "data" / "normativa"
CARPETA_INDICE = BASE / "chroma_db"
COLECCION = "normativa"

RE_BLOQUE = re.compile(r"^## Art\. (.+)$", re.MULTILINE)
RE_ESTADO = re.compile(r"\((Art[ií]culo|Inciso|Párrafo)[^)]*(derogad|sustituid|incorporad)[^)]*\)", re.IGNORECASE)


def _campo(encabezado: str, nombre: str) -> str:
    m = re.search(rf"^{nombre}:\s*(.+)$", encabezado, re.MULTILINE)
    return m.group(1).strip() if m else ""


def estado_del_articulo(texto: str) -> str:
    """'derogado' si la nota de InfoLEG dice que fue derogado; si no, 'vigente'."""
    if re.search(r"\(Art[ií]culos? derogados?\b", texto, re.IGNORECASE):
        return "derogado"
    return "vigente"


def dividir_articulos(md: str, archivo: str = "") -> list[dict]:
    """Devuelve [{'texto', 'metadata'}] con un elemento por artículo del .md."""
    partes = RE_BLOQUE.split(md)
    encabezado = partes[0]
    norma = _campo(encabezado, "Norma")
    fuente = _campo(encabezado, "Fuente")
    fragmentos = []
    for i in range(1, len(partes), 2):
        numero = partes[i].strip()
        cuerpo = partes[i + 1].strip()
        if not cuerpo:
            continue
        fragmentos.append(
            {
                "texto": cuerpo,
                "metadata": {
                    "norma": norma,
                    "articulo": numero,
                    "fuente": fuente,
                    "archivo": archivo,
                    "estado": estado_del_articulo(cuerpo),
                },
            }
        )
    return fragmentos


def cargar_corpus(carpeta: Path = CARPETA_NORMATIVA) -> list[dict]:
    fragmentos: list[dict] = []
    for ruta in sorted(carpeta.glob("*.md")):
        fragmentos.extend(dividir_articulos(ruta.read_text(encoding="utf-8"), ruta.name))
    return fragmentos


def texto_para_embedding(f: dict) -> str:
    """El texto indexado lleva la norma y el artículo adelante: mejora la búsqueda."""
    m = f["metadata"]
    return f"{m['norma']} - Art. {m['articulo']}\n{f['texto']}"


def construir_indice(embeddings=None, carpeta_indice: Path = CARPETA_INDICE, carpeta: Path = CARPETA_NORMATIVA):
    """Reconstruye desde cero el índice vectorial. Devuelve la cantidad de fragmentos."""
    from langchain_chroma import Chroma

    if embeddings is None:
        from model import get_embeddings

        embeddings = get_embeddings()
    fragmentos = cargar_corpus(carpeta)
    if not fragmentos:
        raise RuntimeError(f"No hay normativa en {carpeta}.")
    if carpeta_indice.exists():
        shutil.rmtree(carpeta_indice)
    base = Chroma(collection_name=COLECCION, embedding_function=embeddings, persist_directory=str(carpeta_indice))
    # Se indexa por tandas chicas para no pasarse del límite de la API gratuita.
    for i in range(0, len(fragmentos), 20):
        lote = fragmentos[i : i + 20]
        base.add_texts(
            texts=[texto_para_embedding(f) for f in lote],
            metadatas=[f["metadata"] | {"texto_literal": f["texto"]} for f in lote],
            ids=[f"{f['metadata']['archivo']}::{f['metadata']['articulo']}" for f in lote],
        )
    return len(fragmentos)


if __name__ == "__main__":
    n = construir_indice()
    print(f"Índice construido: {n} artículos en {CARPETA_INDICE}")
