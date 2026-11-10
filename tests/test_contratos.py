import pytest

from contratos import ContratoError, dividir_en_clausulas, leer_contrato

CONTRATO_ORDINALES = """CONTRATO DE LOCACIÓN
En la ciudad de Mendoza, a 10 de marzo de 2025, entre Juan Pérez (LOCADOR) y
Ana Gómez (LOCATARIA), se acuerda lo siguiente:

PRIMERA: OBJETO. El locador da en locación el inmueble ubicado en calle Falsa 123.

SEGUNDA: PLAZO. El plazo es de 24 meses desde el 1 de abril de 2025.

CLÁUSULA TERCERA - PRECIO. El alquiler inicial es de $400.000 mensuales.
Se actualizará cada 3 meses por IPC.

DÉCIMA SEGUNDA: JURISDICCIÓN. Las partes se someten a los tribunales ordinarios.
"""

CONTRATO_NUMERADO = """Contrato
1. Objeto
El locador alquila una casa.
2. Precio
El alquiler es de $300.000.
3) Actualización
Cada 4 meses por ICL.
"""


def test_detecta_clausulas_con_ordinales():
    claus, adv = dividir_en_clausulas(CONTRATO_ORDINALES)
    titulos = [c["titulo"] for c in claus]
    assert titulos[0] == "ENCABEZADO"
    assert "CLÁUSULA PRIMERA" in titulos
    assert "CLÁUSULA TERCERA" in titulos
    assert "CLÁUSULA DÉCIMA SEGUNDA" in titulos
    assert adv == []
    precio = next(c for c in claus if c["titulo"] == "CLÁUSULA TERCERA")
    assert "400.000" in precio["texto"] and "IPC" in precio["texto"]
    # la fecha "10 de marzo" del encabezado no se confunde con una cláusula
    assert len(claus) == 5


def test_detecta_clausulas_numeradas():
    claus, adv = dividir_en_clausulas(CONTRATO_NUMERADO)
    titulos = [c["titulo"] for c in claus]
    assert titulos == ["ENCABEZADO", "CLÁUSULA 1", "CLÁUSULA 2", "CLÁUSULA 3"]
    assert "ICL" in claus[3]["texto"]


def test_fallback_en_bloques_si_no_hay_clausulas():
    texto = "\n\n".join(f"Párrafo {i} " + "x" * 400 for i in range(10))
    claus, adv = dividir_en_clausulas(texto)
    assert len(claus) >= 2
    assert claus[0]["titulo"].startswith("BLOQUE")
    assert adv and "bloques" in adv[0]
    assert sum(len(c["texto"]) for c in claus) >= 10 * 400


def test_leer_txt(tmp_path):
    f = tmp_path / "contrato.txt"
    f.write_text(CONTRATO_ORDINALES, encoding="utf-8")
    r = leer_contrato(f)
    assert r["archivo"] == "contrato.txt"
    assert r["paginas"] is None
    assert len(r["clausulas"]) == 5


def test_leer_txt_latin1(tmp_path):
    f = tmp_path / "c.txt"
    f.write_bytes("PRIMERA: OBJETO.\nSEGUNDA: PRECIO $1.000 años".encode("latin-1"))
    r = leer_contrato(f)
    assert len(r["clausulas"]) >= 2


def test_errores_claros(tmp_path):
    with pytest.raises(ContratoError, match="No se encontró"):
        leer_contrato(tmp_path / "no_existe.pdf")
    otro = tmp_path / "c.docx"
    otro.write_text("x")
    with pytest.raises(ContratoError, match="Formato no soportado"):
        leer_contrato(otro)
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"esto no es un pdf")
    with pytest.raises(ContratoError):
        leer_contrato(roto)
