"""Búsqueda semántica sobre la normativa indexada."""

from __future__ import annotations

from pathlib import Path

from rag.ingest import CARPETA_INDICE, COLECCION
from rag.reintentos import con_reintentos

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


_cache_consultas: dict = {}


def _vector(base, consulta: str, carpeta: str):
    """Embedding de la consulta, con caché (la misma consulta no gasta otro pedido) y reintentos."""
    clave = (carpeta, consulta)
    if clave not in _cache_consultas:
        _cache_consultas[clave] = con_reintentos(lambda: base.embeddings.embed_query(consulta))
    return _cache_consultas[clave]


def _como_dict(d, consulta: str) -> dict:
    m = d.metadata
    return {
        "norma": m.get("norma", ""),
        "articulo": m.get("articulo", ""),
        "fuente": m.get("fuente", ""),
        "estado": m.get("estado", "vigente"),
        "texto": m.get("texto_literal") or d.page_content,
        "consulta": consulta,
    }


def buscar_varias(
    consultas: list[str], k: int = 3, embeddings=None, carpeta_indice: Path = CARPETA_INDICE
) -> list[dict]:
    """Busca varios temas de una vez. Devuelve los artículos sin repetir, cada uno con la
    consulta que lo encontró: [{'norma','articulo','fuente','estado','texto','consulta'}]."""
    if not Path(carpeta_indice).exists():
        raise FileNotFoundError("El índice no existe. Ejecutá: python -m rag.ingest")
    base = _base(embeddings, carpeta_indice)
    vistos: set = set()
    salida: list[dict] = []
    for consulta in consultas:
        vector = _vector(base, consulta, str(carpeta_indice))
        for d in base.similarity_search_by_vector(vector, k=k):
            fila = _como_dict(d, consulta)
            clave = (fila["norma"], fila["articulo"])
            if clave not in vistos:  # un artículo que sirve para dos temas se devuelve una vez
                vistos.add(clave)
                salida.append(fila)
    return salida


def buscar_normativa(consulta: str, k: int = 4, embeddings=None, carpeta_indice: Path = CARPETA_INDICE) -> list[dict]:
    """Un solo tema. Devuelve hasta k artículos: [{'norma','articulo','fuente','estado','texto'}]."""
    filas = buscar_varias([consulta], k=k, embeddings=embeddings, carpeta_indice=carpeta_indice)
    return [{c: v for c, v in f.items() if c != "consulta"} for f in filas]
