"""Lectura de contratos (PDF / TXT) y división en cláusulas.

Esta capa NO interpreta el contrato: solo extrae texto y lo parte en cláusulas
numeradas. La interpretación (monto, índice, periodicidad, etc.) la hace el LLM.
"""

from __future__ import annotations

import re
from pathlib import Path

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
TAMANO_BLOQUE_FALLBACK = 1500  # caracteres, si no se detectan cláusulas

_UNIDAD = r"(?:PRIMER[AO]|SEGUND[AO]|TERCER[AO]|CUART[AO]|QUINT[AO]|SEXT[AO]|S[ÉE]PTIM[AO]|OCTAV[AO]|NOVEN[AO])"
_DECENA = r"(?:D[ÉE]CIM[AO]|VIG[ÉE]SIM[AO]|TRIG[ÉE]SIM[AO]|CUADRAG[ÉE]SIM[AO])"
_ORDINAL = rf"(?:{_DECENA}(?:\s+{_UNIDAD})?|{_UNIDAD}|[ÚU]LTIM[AO])"

# Encabezado de cláusula al inicio de línea:
#   "CLÁUSULA PRIMERA:", "PRIMERA.", "DÉCIMA SEGUNDA -", "1.", "12)", "Cláusula 3"
_ENCABEZADO = re.compile(
    rf"^[ \t]*(?:CL[ÁA]USULA[ \t]+)?(?P<id>{_ORDINAL}|\d{{1,2}})[ \t]*(?:[:.\-–)]|$)",
    re.IGNORECASE | re.MULTILINE,
)


class ContratoError(Exception):
    """Error al leer el contrato, con un mensaje apto para mostrar al usuario."""


# ---------------------------------------------------------------------------
# Extracción de texto
# ---------------------------------------------------------------------------

def extraer_texto(ruta: str | Path) -> tuple[str, int | None]:
    """Devuelve (texto, cantidad_de_paginas). Páginas es None para TXT."""
    path = Path(ruta)
    if not path.exists() or not path.is_file():
        raise ContratoError(f"No se encontró el archivo: {path.name}")
    if path.stat().st_size > MAX_BYTES:
        raise ContratoError("El archivo supera los 10 MB; suba un contrato más liviano.")

    sufijo = path.suffix.lower()
    if sufijo == ".txt":
        crudo = path.read_bytes()
        for codificacion in ("utf-8", "latin-1"):
            try:
                return crudo.decode(codificacion), None
            except UnicodeDecodeError:
                continue
        raise ContratoError("No se pudo decodificar el TXT.")

    if sufijo == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise ContratoError("Falta la dependencia pypdf (pip install pypdf).") from exc
        try:
            lector = PdfReader(str(path))
            if lector.is_encrypted:
                raise ContratoError("El PDF está protegido con contraseña.")
            paginas = [(p.extract_text() or "") for p in lector.pages]
        except ContratoError:
            raise
        except Exception as exc:
            raise ContratoError(f"No se pudo leer el PDF: {exc}") from exc
        texto = "\n".join(paginas)
        if not texto.strip():
            raise ContratoError(
                "El PDF no tiene texto seleccionable (posiblemente es un escaneo). "
                "Suba un PDF con texto o un TXT."
            )
        return texto, len(paginas)

    raise ContratoError("Formato no soportado: use PDF o TXT.")


# ---------------------------------------------------------------------------
# División en cláusulas
# ---------------------------------------------------------------------------

def dividir_en_clausulas(texto: str) -> tuple[list[dict], list[str]]:
    """Parte el texto en cláusulas. Devuelve (clausulas, advertencias).

    Cada cláusula: {"orden": int, "titulo": str, "texto": str}. Lo que aparece
    antes de la primera cláusula (partes, encabezado) se devuelve como
    cláusula con titulo "ENCABEZADO" y orden 0.

    Si se detectan menos de 2 encabezados, se parte en bloques de tamaño fijo
    (titulo "BLOQUE n") y se agrega una advertencia.
    """
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").strip()
    advertencias: list[str] = []
    coincidencias = list(_ENCABEZADO.finditer(texto))

    # Descartar numerales sueltos tipo "2025." que pudieran colarse (>2 dígitos ya no matchean)
    if len(coincidencias) < 2:
        advertencias.append(
            "No se detectaron cláusulas numeradas; el texto se dividió en bloques de tamaño fijo."
        )
        return _bloques_fijos(texto), advertencias

    clausulas: list[dict] = []
    previo = texto[: coincidencias[0].start()].strip()
    if previo:
        clausulas.append({"orden": 0, "titulo": "ENCABEZADO", "texto": previo})

    for i, m in enumerate(coincidencias):
        fin = coincidencias[i + 1].start() if i + 1 < len(coincidencias) else len(texto)
        cuerpo = texto[m.start(): fin].strip()
        clausulas.append(
            {
                "orden": i + 1,
                "titulo": f"CLÁUSULA {m.group('id').upper()}",
                "texto": cuerpo,
            }
        )
    return clausulas, advertencias


def _bloques_fijos(texto: str) -> list[dict]:
    if not texto:
        return []
    bloques: list[dict] = []
    actual = ""
    for parrafo in re.split(r"\n\s*\n", texto):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        if actual and len(actual) + len(parrafo) > TAMANO_BLOQUE_FALLBACK:
            bloques.append(actual)
            actual = parrafo
        else:
            actual = f"{actual}\n\n{parrafo}" if actual else parrafo
    if actual:
        bloques.append(actual)
    return [
        {"orden": i + 1, "titulo": f"BLOQUE {i + 1}", "texto": b}
        for i, b in enumerate(bloques)
    ]


# ---------------------------------------------------------------------------
# API de alto nivel
# ---------------------------------------------------------------------------

def leer_contrato(ruta: str | Path) -> dict:
    """Extrae el texto del contrato y lo divide en cláusulas.

    Devuelve {"archivo", "paginas", "caracteres", "clausulas", "advertencias"}.
    Lanza ContratoError con un mensaje claro si algo falla.
    """
    texto, paginas = extraer_texto(ruta)
    clausulas, advertencias = dividir_en_clausulas(texto)
    return {
        "archivo": Path(ruta).name,
        "paginas": paginas,
        "caracteres": len(texto),
        "clausulas": clausulas,
        "advertencias": advertencias,
    }
