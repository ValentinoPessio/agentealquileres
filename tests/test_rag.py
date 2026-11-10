"""Pruebas del RAG con embeddings simulados (sin llamar a Gemini)."""

import hashlib

import pytest
from langchain_core.embeddings import Embeddings

import tools
from rag import buscar, ingest


class EmbeddingsFalsos(Embeddings):
    """Bolsa de palabras hasheada: textos con palabras en común quedan cerca."""

    DIM = 256

    def _vec(self, texto: str) -> list[float]:
        v = [0.0] * self.DIM
        for palabra in texto.lower().split():
            h = int(hashlib.md5(palabra.strip(".,;:()").encode()).hexdigest(), 16)
            v[h % self.DIM] += 1.0
        return v

    def embed_documents(self, textos):
        return [self._vec(t) for t in textos]

    def embed_query(self, texto):
        return self._vec(texto)


MD = """# Norma de prueba

Norma: Ley de Prueba 1
Fuente: https://ejemplo.test/1
Consultado: 10/11/2026

## Art. 10
ARTICULO 10.- Depósito en garantía. El locador puede pedir un deposito en garantia.

## Art. 11
ARTICULO 11.- Rescisión. El locatario puede resolver el contrato con preaviso.

## Art. 12
ARTICULO 12.- (Artículo derogado por art. 1 de la Ley 2)
"""


def test_dividir_articulos_extrae_metadata_y_estado():
    f = ingest.dividir_articulos(MD, "prueba.md")
    assert [x["metadata"]["articulo"] for x in f] == ["10", "11", "12"]
    assert f[0]["metadata"]["norma"] == "Ley de Prueba 1"
    assert f[0]["metadata"]["fuente"] == "https://ejemplo.test/1"
    assert [x["metadata"]["estado"] for x in f] == ["vigente", "vigente", "derogado"]


def test_corpus_real_tiene_los_articulos_clave():
    f = ingest.cargar_corpus()
    claves = {(x["metadata"]["archivo"], x["metadata"]["articulo"]) for x in f}
    assert ("ccyc_locacion.md", "1221") in claves
    assert ("dnu_70_2023_alquileres.md", "249") in claves
    assert len(f) == 70


@pytest.fixture
def indice(tmp_path):
    normativa = tmp_path / "normativa"
    normativa.mkdir()
    (normativa / "prueba.md").write_text(MD, encoding="utf-8")
    destino = tmp_path / "indice"
    emb = EmbeddingsFalsos()
    assert ingest.construir_indice(emb, destino, normativa) == 3
    return emb, destino


def test_buscar_devuelve_el_articulo_relevante_con_cita(indice):
    emb, destino = indice
    r = buscar.buscar_normativa("deposito en garantia", k=1, embeddings=emb, carpeta_indice=destino)
    assert r[0]["articulo"] == "10" and r[0]["norma"] == "Ley de Prueba 1"
    assert "Depósito en garantía" in r[0]["texto"]


def test_buscar_sin_indice_da_error_claro(tmp_path):
    with pytest.raises(FileNotFoundError):
        buscar.buscar_normativa("algo", carpeta_indice=tmp_path / "no_existe")


def test_tool_buscar_normativa_no_rompe_si_falla(monkeypatch):
    def falla(*a, **k):
        raise FileNotFoundError("sin índice")

    monkeypatch.setattr(buscar, "buscar_normativa", falla)
    r = tools.buscar_normativa.invoke({"consulta": "rescisión"})
    assert "error" in r and "sin índice" in r["error"]


def test_tool_buscar_normativa_formatea_citas(monkeypatch):
    monkeypatch.setattr(
        buscar,
        "buscar_normativa",
        lambda c, k=4, **kw: [
            {"norma": "CCyC", "articulo": "1221", "fuente": "u", "estado": "vigente", "texto": "t"}
        ],
    )
    r = tools.buscar_normativa.invoke({"consulta": "rescisión"})
    assert r["articulos"][0]["cita"] == "CCyC, art. 1221"
