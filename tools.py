"""Tools del agente.

Cada tool es un envoltorio fino sobre la lógica pura de `contratos.py` y
`calculos.py`. Todas devuelven siempre un dict: si algo falla, devuelven
{"error": "..."} en vez de lanzar una excepción, para que el agente pueda
explicarle el problema al usuario o corregir los argumentos sin romper el flujo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from langchain.tools import tool
from pydantic import BaseModel, Field

import calculos
import contratos

BASE = Path(__file__).resolve().parent

# Seguridad (principio de mínimo privilegio): leer_contrato solo puede abrir
# archivos dentro de estas carpetas, aunque el modelo pida otra ruta.
CARPETAS_PERMITIDAS = (
    BASE / "outputs" / "uploads",
    BASE / "data" / "contratos_ejemplo",
)

# Escenarios de proyección: puntos porcentuales que se suman a cada mes.
ESCENARIOS_PP = {"base": 0.0, "optimista": -0.3, "pesimista": 0.3}


class VariacionMensual(BaseModel):
    mes: str = Field(description="Mes en formato AAAA-MM, por ejemplo 2025-03.")
    pct: float = Field(description="Variación mensual en porcentaje; 2.3 significa 2,3 %.")


# ---------------------------------------------------------------------------
# leer_contrato
# ---------------------------------------------------------------------------

class LeerContratoArgs(BaseModel):
    ruta: str = Field(
        description="Ruta del contrato tal como figura en el mensaje del usuario "
        "(por ejemplo 'outputs/uploads/contrato.pdf')."
    )


def _ruta_permitida(ruta: str) -> Path | None:
    candidata = Path(ruta)
    if not candidata.is_absolute():
        candidata = BASE / candidata
    try:
        candidata = candidata.resolve()
    except OSError:
        return None
    for carpeta in CARPETAS_PERMITIDAS:
        if candidata.is_relative_to(carpeta.resolve()):
            return candidata
    return None


@tool(args_schema=LeerContratoArgs)
def leer_contrato(ruta: str) -> dict:
    """Lee un contrato de alquiler (PDF o TXT) que el usuario ya subió y lo divide
    en cláusulas numeradas. Devuelve el archivo, la cantidad de páginas, las
    cláusulas (orden, título y texto) y advertencias si la división fue aproximada.
    Usala una sola vez por contrato, antes de analizarlo."""
    permitida = _ruta_permitida(ruta)
    if permitida is None:
        return {"error": "Ruta no permitida: solo se pueden leer contratos subidos por el usuario."}
    try:
        return contratos.leer_contrato(permitida)
    except contratos.ContratoError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - la tool nunca debe romper el flujo
        return {"error": f"No se pudo leer el contrato: {exc}"}


# ---------------------------------------------------------------------------
# calcular_cronograma
# ---------------------------------------------------------------------------

class CalcularCronogramaArgs(BaseModel):
    monto_inicial: float = Field(description="Alquiler mensual inicial en pesos.")
    fecha_inicio: str = Field(description="Mes de inicio del contrato: AAAA-MM o AAAA-MM-DD.")
    meses_totales: int = Field(
        description="Cantidad de meses a mostrar desde fecha_inicio, incluyendo el mes de inicio."
    )
    periodicidad_meses: int = Field(description="Cada cuántos meses se actualiza el alquiler.")
    tipo_indice: Literal["IPC", "ICL", "FIJO"] = Field(
        description="Índice pactado: IPC, ICL o FIJO (porcentaje fijo en cada ajuste)."
    )
    variaciones_reales: list[VariacionMensual] | None = Field(
        default=None,
        description="Variaciones mensuales ya publicadas del índice (IPC, o ICL convertido a variación mensual).",
    )
    variaciones_proyectadas: list[VariacionMensual] | None = Field(
        default=None,
        description="Variaciones mensuales proyectadas, normalmente el resultado de proyectar_inflacion.",
    )
    porcentaje_fijo: float | None = Field(
        default=None, description="Porcentaje de cada ajuste; solo para tipo_indice FIJO."
    )
    rezago_meses: int = Field(
        default=1,
        description="Meses de rezago: el ajuste de un mes usa las variaciones que terminan este "
        "número de meses antes. Por defecto 1 (el ajuste de julio usa hasta junio).",
    )


def _a_dict(variaciones: list[VariacionMensual] | list[dict] | None) -> dict[str, float]:
    resultado: dict[str, float] = {}
    for v in variaciones or []:
        mes, pct = (v.mes, v.pct) if isinstance(v, VariacionMensual) else (v["mes"], v["pct"])
        resultado[mes] = float(pct)
    return resultado


@tool(args_schema=CalcularCronogramaArgs)
def calcular_cronograma(
    monto_inicial: float,
    fecha_inicio: str,
    meses_totales: int,
    periodicidad_meses: int,
    tipo_indice: str,
    variaciones_reales: list[VariacionMensual] | None = None,
    variaciones_proyectadas: list[VariacionMensual] | None = None,
    porcentaje_fijo: float | None = None,
    rezago_meses: int = 1,
) -> dict:
    """Calcula mes a mes cuánto se paga de alquiler aplicando el índice pactado en
    cada ajuste. Devuelve la tabla en markdown lista para mostrar (tabla_markdown),
    el monto final, la cantidad de ajustes y advertencias si faltan datos.
    Distingue meses con datos reales de meses proyectados. No hagas este cálculo
    de cabeza: usá siempre esta tool."""
    try:
        filas = calculos.generar_cronograma(
            monto_inicial=monto_inicial,
            fecha_inicio=fecha_inicio,
            meses_totales=meses_totales,
            periodicidad_meses=periodicidad_meses,
            tipo_indice=tipo_indice,
            variaciones_reales_pct=_a_dict(variaciones_reales),
            variaciones_proyectadas_pct=_a_dict(variaciones_proyectadas),
            porcentaje_fijo_pct=porcentaje_fijo,
            rezago_meses=rezago_meses,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"No se pudo calcular el cronograma: {exc}"}

    advertencias = [f"{f['mes']}: {f['nota']}" for f in filas if f["fuente"] == "sin dato"]
    return {
        "tabla_markdown": calculos.tabla_markdown(filas),
        "monto_inicial": calculos.formatear_pesos(filas[0]["monto"]),
        "monto_final": calculos.formatear_pesos(filas[-1]["monto"]),
        "cantidad_de_ajustes": sum(1 for f in filas if f["ajuste"]),
        "advertencias": advertencias,
    }


# ---------------------------------------------------------------------------
# proyectar_inflacion
# ---------------------------------------------------------------------------

class ProyectarInflacionArgs(BaseModel):
    primer_mes: str = Field(description="Primer mes a proyectar, formato AAAA-MM.")
    rem_mensual_pct: list[float] = Field(
        description="Inflación mensual esperada por el REM del BCRA para los primeros meses, en %, "
        "empezando en primer_mes (normalmente 6 valores)."
    )
    inflacion_12m_pct: float = Field(
        description="Inflación esperada por el REM para los próximos 12 meses, en %."
    )
    meses: int = Field(default=12, description="Cantidad de meses a proyectar (1 a 12).")
    escenario: Literal["base", "optimista", "pesimista"] = Field(
        default="base",
        description="base = REM tal cual; optimista = 0,3 p.p. menos por mes; pesimista = 0,3 p.p. más.",
    )
    indice: Literal["IPC", "ICL"] = Field(
        default="IPC", description="Índice a proyectar: IPC o ICL."
    )
    ripte_vs_ipc_pp: float = Field(
        default=0.0,
        description="Solo para ICL: puntos porcentuales mensuales en que se supone que los salarios "
        "(RIPTE) superan al IPC. 0 = salario real constante.",
    )


@tool(args_schema=ProyectarInflacionArgs)
def proyectar_inflacion(
    primer_mes: str,
    rem_mensual_pct: list[float],
    inflacion_12m_pct: float,
    meses: int = 12,
    escenario: str = "base",
    indice: str = "IPC",
    ripte_vs_ipc_pp: float = 0.0,
) -> dict:
    """Proyecta la variación mensual del IPC o del ICL para los próximos meses a
    partir de las expectativas del REM del BCRA: usa los meses informados y despeja
    el resto del año con la expectativa a 12 meses. Devuelve la lista de
    variaciones mensuales proyectadas (lista para pasar a calcular_cronograma) y los
    supuestos usados. Es una proyección, no un dato oficial."""
    try:
        ipc = calculos.proyectar_ipc_mensual(
            primer_mes=primer_mes,
            rem_mensual_pct=rem_mensual_pct,
            inflacion_12m_pct=inflacion_12m_pct,
            meses=meses,
            ajuste_pp=ESCENARIOS_PP[escenario],
        )
        serie = ipc if indice == "IPC" else calculos.proyectar_icl_mensual(ipc, ripte_vs_ipc_pp)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"No se pudo proyectar la inflación: {exc}"}

    supuestos = [
        "Meses iniciales: expectativas mensuales del REM.",
        "Meses restantes: tasa mensual constante despejada de la expectativa a 12 meses.",
        f"Escenario: {escenario} ({ESCENARIOS_PP[escenario]:+.1f} p.p. por mes).",
    ]
    if indice == "ICL":
        supuestos.append(
            f"ICL = promedio de IPC y RIPTE; se supone RIPTE = IPC {ripte_vs_ipc_pp:+.1f} p.p. por mes."
        )
    return {
        "indice": indice,
        "variaciones_proyectadas": [{"mes": m, "pct": v} for m, v in serie.items()],
        "acumulado_pct": round((calculos.factor_acumulado(serie.values()) - 1) * 100, 2),
        "supuestos": supuestos,
    }


# ---------------------------------------------------------------------------
# buscar_normativa (RAG)
# ---------------------------------------------------------------------------

class BuscarNormativaArgs(BaseModel):
    consulta: str = Field(
        description="Tema legal a buscar, en lenguaje natural. Ejemplo: "
        "'rescisión anticipada del inquilino y penalidad' o 'depósito en garantía'."
    )
    cantidad: int = Field(default=4, ge=1, le=8, description="Cantidad de artículos a devolver.")


@tool(args_schema=BuscarNormativaArgs)
def buscar_normativa(consulta: str, cantidad: int = 4) -> dict:
    """Busca en la normativa argentina de alquileres (Código Civil y Comercial, DNU 70/2023,
    Ley 24.240) los artículos relacionados con la consulta y los devuelve con su cita."""
    from rag.buscar import buscar_normativa as buscar

    try:
        articulos = buscar(consulta, k=cantidad)
    except Exception as e:  # noqa: BLE001 - el agente debe poder explicar el problema
        return {"error": f"No se pudo consultar la normativa: {e}"}
    if not articulos:
        return {"articulos": [], "aviso": "No se encontraron artículos relacionados."}
    return {
        "articulos": [
            {
                "cita": f"{a['norma']}, art. {a['articulo']}",
                "estado": a["estado"],
                "texto": a["texto"],
                "fuente": a["fuente"],
            }
            for a in articulos
        ]
    }


TOOLS = [leer_contrato, calcular_cronograma, proyectar_inflacion, buscar_normativa]
