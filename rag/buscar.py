"""Búsqueda semántica sobre la normativa indexada."""

from __future__ import annotations

from pathlib import Path

from rag.ingest import CARPETA_INDICE, COLECCION

_cache: dict = {}


def _base(embeddings=None, carpeta_indice: Path = CARPETA_INDICE):
    from langchain_chroma import Chroma

    clave = str(carpeta_indice)
    if embeddings is not None:
        return Chroma(collection_name=COLECCION, embedding_function=embeddings, persist_directory=clave)
    if clave not in _cache:
        from model import get_embeddings

        _cache[clave] = Chroma(
            collection_name=COLECCION, embedding_function=get_embeddings(), persist_directory=clave
        )
    return _cache[clave]


def buscar_normativa(consulta: str, k: int = 4, embeddings=None, carpeta_indice: Path = CARPETA_INDICE) -> list[dict]:
    """Devuelve hasta k artículos: [{'norma','articulo','fuente','estado','texto'}]."""
    if not Path(carpeta_indice).exists():
        raise FileNotFoundError("El índice no existe. Ejecutá: python -m rag.ingest")
    resultados = _base(embeddings, carpeta_indice).similarity_search(consulta, k=k)
    salida = []
    for d in resultados:
        m = d.metadata
        salida.append(
            {
                "norma": m.get("norma", ""),
                "articulo": m.get("articulo", ""),
                "fuente": m.get("fuente", ""),
                "estado": m.get("estado", "vigente"),
                "texto": m.get("texto_literal") or d.page_content,
            }
        )
    return salida
