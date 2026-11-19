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
    assert len(f) == 66  # 70 artículos menos 4 reseñas vacías de derogados
    assert ("ccyc_locacion.md", "1202") not in claves


@pytest.fixture
def indice(tmp_path):
    normativa = tmp_path / "normativa"
    normativa.mkdir()
    (normativa / "prueba.md").write_text(MD, encoding="utf-8")
    destino = tmp_path / "indice"
    emb = EmbeddingsFalsos()
    assert ingest.construir_indice(emb, destino, normativa) == 2
    return emb, destino


def test_buscar_devuelve_el_articulo_relevante_con_cita(indice):
    emb, destino = indice
    r = buscar.buscar_normativa("deposito en garantia", k=1, embeddings=emb, carpeta_indice=destino)
    assert r[0]["articulo"] == "10" and r[0]["norma"] == "Ley de Prueba 1"
    assert "Depósito en garantía" in r[0]["texto"]


def test_buscar_sin_indice_da_error_claro(tmp_path):
    with pytest.raises(FileNotFoundError):
        buscar.buscar_normativa("algo", carpeta_indice=tmp_path / "no_existe")


def test_resenas_derogadas_no_se_indexan():
    f = ingest.dividir_articulos(MD, "prueba.md")
    assert [ingest.es_resena_derogada(x) for x in f] == [False, False, True]


def test_buscar_varias_junta_temas_sin_repetir(indice):
    emb, destino = indice
    r = buscar.buscar_varias(
        ["deposito en garantia", "rescision con preaviso", "deposito"], k=1, embeddings=emb, carpeta_indice=destino
    )
    assert [x["articulo"] for x in r] == ["10", "11"]  # el 3.º tema repite el art. 10
    assert r[0]["consulta"] == "deposito en garantia"


def test_consulta_repetida_no_vuelve_a_pedir_embedding(indice):
    emb, destino = indice
    llamadas = []
    original = emb.embed_query
    emb.embed_query = lambda t: (llamadas.append(t), original(t))[1]
    buscar._cache_consultas.clear()
    buscar.buscar_varias(["deposito"], embeddings=emb, carpeta_indice=destino)
    buscar.buscar_varias(["deposito"], embeddings=emb, carpeta_indice=destino)
    assert llamadas == ["deposito"]


def test_reintentos_ante_429_y_luego_funciona():
    from rag.reintentos import con_reintentos

    estado = {"n": 0}
    esperas = []

    def f():
        estado["n"] += 1
        if estado["n"] < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "ok"

    assert con_reintentos(f, dormir=esperas.append) == "ok"
    assert esperas == [2.0, 4.0]


def test_reintentos_agotados_y_errores_no_429():
    from rag.reintentos import LimiteDeCuota, con_reintentos

    def siempre_429():
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with pytest.raises(LimiteDeCuota):
        con_reintentos(siempre_429, intentos=2, dormir=lambda s: None)
    veces = []

    def otro():
        veces.append(1)
        raise ValueError("otro error")

    with pytest.raises(ValueError):
        con_reintentos(otro, dormir=lambda s: None)
    assert len(veces) == 1  # un error que no es 429 no se reintenta


def test_tool_buscar_normativa_no_rompe_si_falla(monkeypatch):
    def falla(*a, **k):
        raise FileNotFoundError("sin índice")

    monkeypatch.setattr(buscar, "buscar_varias", falla)
    r = tools.buscar_normativa.invoke({"consultas": ["rescisión"]})
    assert "error" in r and "sin índice" in r["error"]


def test_tool_buscar_normativa_distingue_limite_de_cuota(monkeypatch):
    from rag.reintentos import LimiteDeCuota

    def cuota(*a, **k):
        raise LimiteDeCuota("Se alcanzó el límite (429).")

    monkeypatch.setattr(buscar, "buscar_varias", cuota)
    r = tools.buscar_normativa.invoke({"consultas": ["rescisión"]})
    assert r["tipo"] == "limite_de_cuota" and "esperá" in r["error"]


def test_tool_buscar_normativa_formatea_citas(monkeypatch):
    monkeypatch.setattr(
        buscar,
        "buscar_varias",
        lambda cs, k=3, **kw: [
            {"norma": "CCyC", "articulo": "1221", "fuente": "u", "estado": "vigente", "texto": "t", "consulta": cs[0]}
        ],
    )
    r = tools.buscar_normativa.invoke({"consultas": ["rescisión", "depósito"]})
    assert r["articulos"][0]["cita"] == "CCyC, art. 1221"
    assert r["articulos"][0]["encontrado_por"] == "rescisión"


def test_tool_buscar_normativa_acepta_siete_temas_en_una_llamada(monkeypatch):
    """Antes el esquema aceptaba 6 y la llamada con 7 temas fallaba (y gastaba un pedido al modelo)."""
    recibidos = {}

    def falso(cs, k=3, **kw):
        recibidos["n"] = len(cs)
        return []

    monkeypatch.setattr(buscar, "buscar_varias", falso)
    temas = [f"tema {i}" for i in range(7)]
    r = tools.buscar_normativa.invoke({"consultas": temas})
    assert "error" not in r and recibidos["n"] == 7
