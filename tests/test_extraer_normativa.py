"""Pruebas del extractor de normativa con una página InfoLEG sintética."""

import importlib.util
import sys
from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "extraer_normativa.py"
spec = importlib.util.spec_from_file_location("extraer_normativa", RUTA)
en = importlib.util.module_from_spec(spec)
sys.modules["extraer_normativa"] = en
spec.loader.exec_module(en)

LINEAS = [
    "TITULO IV",
    "CONTRATOS",
    "ARTICULO 1187.- Convenio. Texto de prueba que sigue",
    "en otra linea.",
    "(Artículo sustituido por art. 1 de la Ley X)",
    "ARTICULO 1204 bis.- Otro articulo.",
    "Capítulo II - Algo",
    "ARTICULO 1205.- Siguiente.",
]


def test_extrae_rangos_y_sufijos():
    bloques, faltantes = en.extraer_bloques(LINEAS, [(1187, 1205)])
    etiquetas = [(b["numero"], b["sufijo"]) for b in bloques]
    assert (1187, "") in etiquetas and (1205, "") in etiquetas
    assert any(s.lower() == "bis" for _, s in etiquetas)
    assert faltantes  # 1188..1204 no están en la página


def test_no_incluye_titulos_pegados_al_final():
    bloques, _ = en.extraer_bloques(LINEAS, [(1204, 1204)])
    assert all("Capítulo II" not in l for b in bloques for l in b["lineas"])
