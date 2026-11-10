"""Genera data/indices/indices.json a partir de las series oficiales descargadas.

Fuentes (se guardan a mano en data/indices/fuentes/ o data/normativa/fuentes/, no se versionan):
  * IPC nivel general nacional (INDEC): CSV "serie_ipc_divisiones.csv" (Codigo 0, Region Nacional).
  * ICL (BCRA, variable 40): CSV diario "indice-para-contratos-de-locacion-*.csv".
  * REM (BCRA): Excel "relevamiento-expectativas-mercado-tablas-AAAA-MM.xlsx".

Uso:
  python scripts/generar_indices.py --fuentes <carpeta> [--salida data/indices/indices.json]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _buscar(carpeta: Path, patron: str) -> Path:
    candidatos = sorted(carpeta.glob(patron))
    if not candidatos:
        raise FileNotFoundError(f"No encuentro '{patron}' en {carpeta}.")
    return candidatos[-1]


def leer_ipc(ruta: Path) -> dict:
    """Variaciones mensuales (%) calculadas desde el índice, contrastadas con la publicada."""
    niveles: dict[str, float] = {}
    publicadas: dict[str, float] = {}
    with open(ruta, encoding="latin-1", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["Codigo"] == "0" and r["Region"] == "Nacional":
                mes = f"{r['Periodo'][:4]}-{r['Periodo'][4:]}"
                niveles[mes] = float(r["Indice_IPC"].replace(",", "."))
                if r["v_m_IPC"] != "NA":
                    publicadas[mes] = float(r["v_m_IPC"].replace(",", "."))
    meses = sorted(niveles)
    variaciones: dict[str, float] = {}
    for anterior, mes in zip(meses, meses[1:]):
        v = (niveles[mes] / niveles[anterior] - 1) * 100
        if mes in publicadas and abs(v - publicadas[mes]) > 0.06:
            raise AssertionError(f"IPC {mes}: calculado {v:.3f} vs publicado {publicadas[mes]}")
        variaciones[mes] = round(v, 4)
    return {
        "fuente": "INDEC - IPC nivel general, cobertura nacional (base dic-2016=100)",
        "archivo": ruta.name,
        "ultimo_mes": meses[-1],
        "variaciones_mensuales_pct": variaciones,
    }


def leer_icl(ruta: Path) -> dict:
    """Nivel del ICL al día 1 de cada mes, más el último dato diario."""
    diario: dict[str, float] = {}
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            diario[r["Fecha"]] = float(r["Valor"])
    primeros = {f[:7]: v for f, v in diario.items() if f.endswith("-01")}
    ultimo = max(diario)
    return {
        "fuente": "BCRA - Índice para Contratos de Locación (ICL), variable 40",
        "archivo": ruta.name,
        "ultimo_dato": ultimo,
        "niveles_dia_1": primeros,
    }


def leer_rem(ruta: Path) -> dict:
    import openpyxl

    ws = openpyxl.load_workbook(ruta, data_only=True)["Cuadros de resultados"]
    titulo = str(ws.cell(2, 2).value)
    m = re.search(r"(\w+) (\d{4})\s*$", titulo)
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    relevamiento = f"{m.group(2)}-{meses.index(m.group(1).lower()) + 1:02d}"
    if "IPC nivel general" not in str(ws.cell(5, 2).value):
        raise AssertionError("La primera tabla del REM ya no es el IPC nivel general.")
    mensual: dict[str, float] = {}
    r = 7
    while ws.cell(r, 3).value == "var. % mensual":
        mensual[ws.cell(r, 2).value.strftime("%Y-%m")] = round(float(ws.cell(r, 4).value), 4)
        r += 1
    resto = {str(ws.cell(i, 2).value): (str(ws.cell(i, 3).value), float(ws.cell(i, 4).value)) for i in range(r, r + 5)}
    prox12 = resto["próx. 12 meses"]
    fin = re.search(r"([a-z]{3})-(\d{2})", prox12[0])
    return {
        "fuente": f"BCRA - REM {relevamiento} (mediana de los analistas), IPC nivel general nacional",
        "archivo": ruta.name,
        "relevamiento": relevamiento,
        "mensual_mediana_pct": mensual,
        "proximos_12_meses_pct": prox12[1],
        "proximos_12_meses_referencia": prox12[0],
        "diciembre_2026_pct": resto["2026"][1],
        "nota": "La expectativa a 12 meses es interanual a "
        f"{fin.group(0) if fin else '?'}: la ventana arranca en el segundo mes de la tabla.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuentes", required=True, type=Path)
    ap.add_argument("--salida", type=Path, default=BASE / "data" / "indices" / "indices.json")
    ap.add_argument("--fecha", default=date.today().isoformat(), help="Fecha de generación (AAAA-MM-DD).")
    a = ap.parse_args()

    datos = {
        "generado": a.fecha,
        "ipc": leer_ipc(_buscar(a.fuentes, "serie_ipc*.csv")),
        "icl": leer_icl(_buscar(a.fuentes, "indice-para-contratos-de-locacion*.csv")),
        "rem": leer_rem(_buscar(a.fuentes, "relevamiento-expectativas-mercado-tablas-*.xlsx")),
    }
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[OK] {a.salida}: IPC hasta {datos['ipc']['ultimo_mes']}, ICL hasta {datos['icl']['ultimo_dato']}, "
          f"REM {datos['rem']['relevamiento']}")


if __name__ == "__main__":
    main()
