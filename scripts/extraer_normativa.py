"""Extrae artículos de las páginas de InfoLEG guardadas en data/normativa/fuentes/
y genera los archivos de data/normativa/*.md que usa el RAG.

Cómo se usa:
  1. Abrir cada norma en InfoLEG (texto actualizado) y guardarla con Ctrl+S como
     "Página web, solo HTML" en data/normativa/fuentes/ (el nombre da igual: cada
     página se identifica por su contenido).
  2. python scripts/extraer_normativa.py

El texto de los artículos NO lo reescribe ningún modelo: lo copia este programa
de la página oficial. Solo se cambian los saltos de línea (InfoLEG corta las
líneas a ~70 caracteres) y el script verifica que no se pierda ninguna palabra.

Formato de salida (el que lee rag/ingest.py): encabezado con metadatos y un
bloque por artículo que empieza con una línea '## Art. N'.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
FUENTES = BASE / "data" / "normativa" / "fuentes"
SALIDA = BASE / "data" / "normativa"

# Encabezado de artículo: en MAYÚSCULAS y al inicio de línea (las menciones dentro
# de notas o del texto usan minúsculas o no están al inicio).
RE_ARTICULO = re.compile(
    r"^\s*ART[IÍ]CULO\s+(\d+)(?!\d)\s*[º°]?\s*(?:(bis|ter|quater|quinquies)\b)?", re.IGNORECASE
)
RE_ARTICULO_MAYUS = re.compile(r"^\s*ART[IÍ]CULO\s+\d")
RE_ESTRUCTURA = re.compile(r"^\s*(LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N|PAR[AÁ]GRAFO)\s+\S+")
RE_TITULO_FINAL = re.compile(r"^\s*(LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N)\s+[IVXLC\d]+\b\s*[-–.]?", re.IGNORECASE)
RE_INICIO_PARRAFO =re.compile(r"^(\(|[a-zñ]\)\s|\d+[\)\.]\s|[-•–]\s|[IVX]+\.\s)")
LARGO_LINEA_COMPLETA = 55  # una línea más corta que esto cierra el párrafo


@dataclass
class Documento:
    archivo: str
    titulo: str
    norma: str
    fuente: str
    detectar: str  # regex que identifica la página (se busca al inicio del texto)
    rangos: list[tuple[int, int]]
    tope_numeracion: int | None = None  # artículos con número mayor son texto citado
    alcance: str = ""
    extras: list[str] = field(default_factory=list)


CCYC_URL = "https://servicios.infoleg.gob.ar/infolegInternet/verNorma.do?id=235975"
DOCUMENTOS = [
    Documento(
        archivo="ccyc_locacion.md",
        titulo="Código Civil y Comercial de la Nación: contrato de locación",
        norma="Código Civil y Comercial de la Nación (Ley 26.994)",
        fuente=CCYC_URL,
        detectar=r"CODIGO\s+CIVIL\s+Y\s+COMERCIAL",
        rangos=[(1187, 1226)],
        alcance="Artículos 1187 a 1226 (Libro Tercero, Título IV, Capítulo 4: Locación).",
    ),
    Documento(
        archivo="ccyc_clausulas_abusivas.md",
        titulo="Código Civil y Comercial de la Nación: libertad contractual y cláusulas abusivas",
        norma="Código Civil y Comercial de la Nación (Ley 26.994)",
        fuente=CCYC_URL,
        detectar=r"CODIGO\s+CIVIL\s+Y\s+COMERCIAL",
        rangos=[(958, 958), (960, 960), (984, 989)],
        alcance="Artículos 958, 960 y 984 a 989 (libertad de contratación, facultades de los "
        "jueces y contratos por adhesión).",
    ),
    Documento(
        archivo="dnu_70_2023_alquileres.md",
        titulo="DNU 70/2023: modificaciones sobre locación y derogación de la Ley 27.551",
        norma="Decreto de Necesidad y Urgencia 70/2023 (DNU-2023-70-APN-PTE)",
        fuente="https://servicios.infoleg.gob.ar/infolegInternet/verNorma.do?id=395521",
        detectar=r"Decreto\s+70/2023",
        rangos=[(249, 263)],
        tope_numeracion=366,
        alcance="Artículos 249 a 263 del decreto. Los artículos del Código Civil y Comercial "
        "que cada uno sustituye o deroga figuran dentro de su texto.",
    ),
    Documento(
        archivo="ley_24240_consumidor.md",
        titulo="Ley 24.240 de Defensa del Consumidor: artículos sobre cláusulas abusivas",
        norma="Ley 24.240 de Defensa del Consumidor",
        fuente="https://servicios.infoleg.gob.ar/infolegInternet/verNorma.do?id=638",
        detectar=r"Ley\s+N[ºo°]?\s*24\.240",
        rangos=[(1, 3), (37, 38)],
        alcance="Artículos 1 a 3 y 37 a 38.",
    ),
]


# ---------------------------------------------------------------------------
# HTML -> texto
# ---------------------------------------------------------------------------

class _ExtractorTexto(HTMLParser):
    BLOQUES = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._omitir = 0

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        if tag in ("script", "style"):
            self._omitir += 1
        if tag in self.BLOQUES:
            self.partes.append("\n")

    def handle_endtag(self, tag):  # noqa: ANN001
        if tag in ("script", "style") and self._omitir:
            self._omitir -= 1
        if tag in self.BLOQUES - {"br"}:
            self.partes.append("\n")

    def handle_data(self, data):  # noqa: ANN001
        if not self._omitir:
            self.partes.append(data)


def decodificar(crudo: bytes) -> str:
    m = re.search(rb"charset=[\"']?([A-Za-z0-9_-]+)", crudo[:5000])
    codificacion = m.group(1).decode("ascii") if m else "utf-8"
    try:
        return crudo.decode(codificacion)
    except (LookupError, UnicodeDecodeError):
        return crudo.decode("latin-1")


def html_a_lineas(crudo: bytes) -> list[str]:
    extractor = _ExtractorTexto()
    extractor.feed(decodificar(crudo))
    texto = re.sub(r"[ \t\xa0]+", " ", "".join(extractor.partes))
    texto = re.sub(r"\n\s*\n+", "\n", texto).strip()
    return [linea.strip() for linea in texto.split("\n")]


# ---------------------------------------------------------------------------
# Extracción de artículos
# ---------------------------------------------------------------------------

def encabezados(lineas: list[str]) -> list[tuple[int, int, str]]:
    """Devuelve [(indice_de_linea, numero, sufijo)] de las líneas 'ARTICULO N'."""
    resultado = []
    for i, linea in enumerate(lineas):
        if not RE_ARTICULO_MAYUS.match(linea):
            continue
        m = RE_ARTICULO.match(linea)
        if m:
            resultado.append((i, int(m.group(1)), (m.group(2) or "").lower()))
    return resultado


def extraer_bloques(
    lineas: list[str],
    rangos: list[tuple[int, int]],
    tope_numeracion: int | None = None,
) -> tuple[list[dict], list[str]]:
    """Extrae los artículos pedidos. Devuelve (bloques, faltantes).

    Cada bloque: {"numero", "sufijo", "lineas", "inicio"}. Un artículo termina en
    el siguiente encabezado de artículo (de numeración normal) o en un título de
    estructura (LIBRO, TÍTULO, CAPÍTULO, SECCIÓN).
    """
    todos = encabezados(lineas)
    normales = [h for h in todos if tope_numeracion is None or h[1] <= tope_numeracion]
    bloques: list[dict] = []
    faltantes: list[str] = []
    ultimo_inicio = -1

    pedidos = [n for desde, hasta in rangos for n in range(desde, hasta + 1)]
    for numero in pedidos:
        candidatos = [h for h in normales if h[1] == numero and h[0] > ultimo_inicio]
        if not candidatos:
            faltantes.append(str(numero))
            continue
        # el primero es el principal; los bis/ter que le siguen se agregan aparte
        for inicio, num, sufijo in candidatos[: 1 + sum(1 for c in candidatos[1:] if c[2])]:
            siguiente = next((h[0] for h in normales if h[0] > inicio), len(lineas))
            fin = siguiente
            for j in range(inicio + 1, siguiente):
                if RE_ESTRUCTURA.match(lineas[j]) and lineas[j] == lineas[j].upper():
                    fin = j
                    break
            cuerpo = lineas[inicio:fin]
            # Títulos de la norma que contiene al artículo ("Capítulo I - ...",
            # "Título XI – SALUD") que quedaron pegados al final: no son parte del artículo.
            while cuerpo and RE_TITULO_FINAL.match(cuerpo[-1]):
                cuerpo = cuerpo[:-1]
            bloques.append({"numero": num, "sufijo": sufijo, "lineas": cuerpo, "inicio": inicio})
            ultimo_inicio = max(ultimo_inicio, inicio) if not sufijo else ultimo_inicio
    return bloques, faltantes


def desenvolver(lineas: list[str]) -> list[str]:
    """Une las líneas cortadas por el ancho de página en párrafos.

    Solo cambia saltos de línea por espacios: no agrega, quita ni modifica palabras.
    """
    parrafos: list[str] = []
    actual = ""
    largo_previo = 0
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        if not actual:
            actual = linea
        elif actual.startswith("(") and actual.count("(") > actual.count(")"):
            actual = f"{actual} {linea}"  # nota entre paréntesis todavía abierta
        elif RE_INICIO_PARRAFO.match(linea) or largo_previo < LARGO_LINEA_COMPLETA:
            parrafos.append(actual)
            actual = linea
        else:
            actual = f"{actual} {linea}"
        largo_previo = len(linea)
    if actual:
        parrafos.append(actual)
    return parrafos


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def ubicacion(lineas: list[str], inicio: int) -> list[str]:
    """Títulos de estructura (libro, título, capítulo, sección) vigentes antes de `inicio`."""
    ultimo: dict[str, str] = {}
    for i in range(inicio):
        m = RE_ESTRUCTURA.match(lineas[i])
        if m and lineas[i] == lineas[i].upper():
            nivel = m.group(1).upper().replace("Í", "I").replace("Ó", "O").replace("Á", "A")
            nombre = lineas[i + 1] if i + 1 < len(lineas) and not RE_ESTRUCTURA.match(lineas[i + 1]) else ""
            ultimo[nivel] = f"{lineas[i]} - {nombre}".strip(" -")
            for menor in {"LIBRO": ["TITULO", "CAPITULO", "SECCION", "PARAGRAFO"],
                          "TITULO": ["CAPITULO", "SECCION", "PARAGRAFO"],
                          "CAPITULO": ["SECCION", "PARAGRAFO"],
                          "SECCION": ["PARAGRAFO"]}.get(nivel, []):
                ultimo.pop(menor, None)
    orden = ["LIBRO", "TITULO", "CAPITULO", "SECCION", "PARAGRAFO"]
    return [ultimo[n] for n in orden if n in ultimo]


def construir_md(doc: Documento, lineas: list[str], bloques: list[dict], fecha: str) -> str:
    ubic = ubicacion(lineas, bloques[0]["inicio"]) if bloques else []
    cabecera = [
        f"# {doc.titulo}",
        "",
        f"Norma: {doc.norma}",
        f"Fuente: {doc.fuente}",
        f"Consultado: {fecha}",
        "Vigencia: texto actualizado de InfoLEG; cada artículo conserva la nota que indica si "
        "fue sustituido o derogado y por qué norma.",
        f"Alcance: {doc.alcance}",
    ]
    if ubic:
        cabecera.append("Ubicación del primer artículo: " + " / ".join(ubic))
    partes = ["\n".join(cabecera)]
    for b in bloques:
        etiqueta = f"{b['numero']} {b['sufijo']}".strip()
        partes.append(f"## Art. {etiqueta}\n" + "\n".join(desenvolver(b["lineas"])))
    return "\n\n".join(partes) + "\n"


def verificar_sin_perdidas(bloques: list[dict], md: str) -> None:
    """Comprueba que el texto de salida contiene exactamente las palabras de la fuente."""
    for b in bloques:
        origen = _normalizar(" ".join(b["lineas"]))
        etiqueta = f"{b['numero']} {b['sufijo']}".strip()
        m = re.search(rf"## Art\. {re.escape(etiqueta)}\n(.*?)(?=\n\n## Art\. |\Z)", md, re.S)
        destino = _normalizar(m.group(1)) if m else ""
        if origen != destino:
            raise AssertionError(f"El artículo {etiqueta} no coincide con la fuente.")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def identificar(paginas: dict[str, list[str]], doc: Documento) -> str | None:
    patron = re.compile(doc.detectar, re.IGNORECASE)
    for nombre, lineas in paginas.items():
        if patron.search(" ".join(lineas[:15])):
            return nombre
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fuentes", type=Path, default=FUENTES, help="carpeta con los .html de InfoLEG")
    ap.add_argument("--salida", type=Path, default=SALIDA, help="carpeta de salida de los .md")
    ap.add_argument("--fecha", default=date.today().strftime("%d/%m/%Y"), help="fecha de consulta")
    args = ap.parse_args(argv)

    archivos = sorted(p for p in args.fuentes.glob("*") if p.suffix.lower() in (".html", ".htm"))
    if not archivos:
        print(f"No hay archivos .html en {args.fuentes}")
        return 1
    paginas = {p.name: html_a_lineas(p.read_bytes()) for p in archivos}

    args.salida.mkdir(parents=True, exist_ok=True)
    hubo_error = False
    for doc in DOCUMENTOS:
        nombre = identificar(paginas, doc)
        if nombre is None:
            print(f"[FALTA] {doc.archivo}: no encontré la página de «{doc.norma}» en {args.fuentes}")
            hubo_error = True
            continue
        lineas = paginas[nombre]
        bloques, faltantes = extraer_bloques(lineas, doc.rangos, doc.tope_numeracion)
        if not bloques:
            print(f"[ERROR] {doc.archivo}: no se extrajo ningún artículo")
            hubo_error = True
            continue
        md = construir_md(doc, lineas, bloques, args.fecha)
        verificar_sin_perdidas(bloques, md)
        (args.salida / doc.archivo).write_text(md, encoding="utf-8")
        estado = "OK" if not faltantes else "INCOMPLETO"
        print(f"[{estado}] {doc.archivo}: {len(bloques)} artículos desde «{nombre}»"
              + (f" | faltan: {', '.join(faltantes)}" if faltantes else ""))
        hubo_error = hubo_error or bool(faltantes)
    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main())
