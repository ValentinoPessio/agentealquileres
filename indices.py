"""Acceso a las series oficiales de IPC, ICL y REM guardadas en data/indices/indices.json.

El JSON lo genera scripts/generar_indices.py desde los archivos oficiales (INDEC y BCRA),
y lleva la fecha y la fuente de cada serie. Así el agente no depende de que una API
esté disponible durante la demo, y los números no pasan por el modelo.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import calculos

RUTA_INDICES = Path(__file__).resolve().parent / "data" / "indices" / "indices.json"


class DatosNoDisponibles(Exception):
    """No existe el archivo de índices o no contiene lo pedido."""


@lru_cache(maxsize=4)
def _leer(ruta: str) -> dict:
    p = Path(ruta)
    if not p.exists():
        raise DatosNoDisponibles(
            "No existe data/indices/indices.json. Generalo con scripts/generar_indices.py."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def cargar(ruta: Path | None = None) -> dict:
    return _leer(str(ruta or RUTA_INDICES))


def ipc_reales(ruta: Path | None = None) -> dict[str, float]:
    return dict(cargar(ruta)["ipc"]["variaciones_mensuales_pct"])


def icl_reales(ruta: Path | None = None) -> dict[str, float]:
    """Variación mensual del ICL (%): nivel al día 1 del mes siguiente sobre el del mes."""
    return calculos.variaciones_desde_niveles(cargar(ruta)["icl"]["niveles_dia_1"])


def reales(indice: str, ruta: Path | None = None) -> dict[str, float]:
    if indice == "IPC":
        return ipc_reales(ruta)
    if indice == "ICL":
        return icl_reales(ruta)
    raise DatosNoDisponibles(f"No hay serie real para el índice '{indice}'.")


def ultimo_mes_real(indice: str, ruta: Path | None = None) -> str:
    return max(reales(indice, ruta))


def fuente_real(indice: str, ruta: Path | None = None) -> str:
    d = cargar(ruta)
    if indice == "IPC":
        return d["ipc"]["fuente"]
    return f"{d['icl']['fuente']} (último dato diario: {d['icl']['ultimo_dato']})"


def rem(ruta: Path | None = None) -> dict:
    return cargar(ruta)["rem"]


def proyeccion_base_ipc(meses: int = 12, ajuste_pp: float = 0.0, ruta: Path | None = None) -> dict[str, float]:
    """IPC mensual proyectado desde el REM guardado.

    El primer mes del REM (el que todavía no publicó el INDEC) se toma tal cual; la
    expectativa a 12 meses es interanual y su ventana arranca en el mes siguiente, así
    que los meses restantes se despejan de ella (calculos.proyectar_ipc_mensual).
    """
    r = rem(ruta)
    mensual = r["mensual_mediana_pct"]
    meses_rem = sorted(mensual)
    primero = meses_rem[0]
    resto = [mensual[m] for m in meses_rem[1:]]
    ventana = calculos.proyectar_ipc_mensual(
        calculos.sumar_meses(primero, 1), resto, r["proximos_12_meses_pct"], meses=12, ajuste_pp=ajuste_pp
    )
    serie = {primero: round(mensual[primero] + ajuste_pp, 4), **ventana}
    return dict(list(serie.items())[:meses])
