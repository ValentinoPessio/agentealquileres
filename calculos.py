"""Lógica pura de cálculo del agente (sin LangChain, sin red).

Convenciones (decisiones de diseño que el equipo debe poder defender):

* Los porcentajes se expresan EN PORCENTAJE (2.3 significa 2,3 %), tanto en
  entradas como en salidas.
* Los meses se identifican con claves "AAAA-MM".
* El alquiler se paga mensualmente. El primer mes es `fecha_inicio`. Cada
  `periodicidad_meses` meses, a partir del inicio, hay un ajuste.
* IPC: el ajuste del mes M usa las `periodicidad_meses` variaciones mensuales
  del IPC que terminan `rezago_meses` meses antes de M. Con rezago 1 (valor por
  defecto), un ajuste trimestral de julio usa abril, mayo y junio.
* ICL: se calcula a partir de los niveles diarios del índice al día 1 de cada
  mes (ver `variaciones_desde_niveles`). Comparar el ICL del 1 del mes de ajuste
  contra el ICL del 1 del mes base equivale a encadenar las variaciones
  mensuales con rezago 1.
* FIJO: porcentaje fijo cada `periodicidad_meses` meses.
* Los montos se calculan sin redondear en los pasos intermedios y se redondean
  a centavos solo al mostrarlos.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

TIPOS_INDICE = ("IPC", "ICL", "FIJO")


# ---------------------------------------------------------------------------
# Utilidades de meses
# ---------------------------------------------------------------------------

def normalizar_mes(valor: str | date) -> str:
    """Devuelve la clave 'AAAA-MM' de un 'AAAA-MM', 'AAAA-MM-DD' o `date`."""
    if isinstance(valor, date):
        return f"{valor.year:04d}-{valor.month:02d}"
    texto = str(valor).strip()
    partes = texto.split("-")
    if len(partes) < 2:
        raise ValueError(f"Fecha inválida '{valor}': use AAAA-MM o AAAA-MM-DD.")
    try:
        anio, mes = int(partes[0]), int(partes[1])
    except ValueError as exc:
        raise ValueError(f"Fecha inválida '{valor}': use AAAA-MM o AAAA-MM-DD.") from exc
    if not 1 <= mes <= 12 or anio < 1900:
        raise ValueError(f"Fecha inválida '{valor}'.")
    return f"{anio:04d}-{mes:02d}"


def sumar_meses(clave: str, n: int) -> str:
    """Suma `n` meses (puede ser negativo) a una clave 'AAAA-MM'."""
    anio, mes = (int(x) for x in normalizar_mes(clave).split("-"))
    total = anio * 12 + (mes - 1) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


# ---------------------------------------------------------------------------
# Cálculos básicos
# ---------------------------------------------------------------------------

def factor_acumulado(variaciones_pct: Iterable[float]) -> float:
    """Encadena variaciones porcentuales: producto de (1 + v/100)."""
    factor = 1.0
    for v in variaciones_pct:
        factor *= 1.0 + v / 100.0
    return factor


def variaciones_desde_niveles(niveles: Mapping[str, float]) -> dict[str, float]:
    """Convierte niveles de un índice (valor al día 1 de cada mes) en
    variaciones mensuales en %.

    La variación del mes m es nivel[m+1] / nivel[m] - 1. Solo se informan los
    meses para los que existen ambos niveles.
    """
    normalizados = {normalizar_mes(k): float(v) for k, v in niveles.items()}
    resultado: dict[str, float] = {}
    for mes, nivel in normalizados.items():
        siguiente = sumar_meses(mes, 1)
        if siguiente in normalizados:
            if nivel <= 0:
                raise ValueError(f"Nivel de índice inválido en {mes}: {nivel}")
            resultado[mes] = (normalizados[siguiente] / nivel - 1.0) * 100.0
    return resultado


# ---------------------------------------------------------------------------
# Cronograma de actualización
# ---------------------------------------------------------------------------

def generar_cronograma(
    monto_inicial: float,
    fecha_inicio: str | date,
    meses_totales: int,
    periodicidad_meses: int,
    tipo_indice: str,
    variaciones_reales_pct: Mapping[str, float] | None = None,
    variaciones_proyectadas_pct: Mapping[str, float] | None = None,
    porcentaje_fijo_pct: float | None = None,
    rezago_meses: int = 1,
) -> list[dict]:
    """Genera la tabla mes a mes del alquiler.

    Cada fila: {mes, monto, ajuste (bool), variacion_pct, fuente, nota}.

    `fuente` puede ser: 'inicial', 'sin ajuste', 'real', 'proyectado', 'mixto',
    'fijo' o 'sin dato' (faltan variaciones: el monto no se actualiza y la
    nota lo explica; los ajustes siguientes parten de ese monto sin actualizar).

    Si una misma variación mensual figura como real y como proyectada, se usa la
    real.
    """
    tipo = str(tipo_indice).strip().upper()
    if tipo not in TIPOS_INDICE:
        raise ValueError(f"Tipo de índice '{tipo_indice}' no soportado. Use: {', '.join(TIPOS_INDICE)}.")
    if monto_inicial <= 0:
        raise ValueError("El monto inicial debe ser mayor a cero.")
    if meses_totales < 1:
        raise ValueError("meses_totales debe ser al menos 1.")
    if periodicidad_meses < 1:
        raise ValueError("La periodicidad debe ser de al menos 1 mes.")
    if rezago_meses < 0:
        raise ValueError("El rezago no puede ser negativo.")
    if tipo == "FIJO" and porcentaje_fijo_pct is None:
        raise ValueError("Para ajuste FIJO hay que indicar porcentaje_fijo_pct.")

    reales = {normalizar_mes(k): float(v) for k, v in (variaciones_reales_pct or {}).items()}
    proyectadas = {normalizar_mes(k): float(v) for k, v in (variaciones_proyectadas_pct or {}).items()}

    inicio = normalizar_mes(fecha_inicio)
    monto = float(monto_inicial)
    filas: list[dict] = []

    for i in range(meses_totales):
        mes = sumar_meses(inicio, i)
        fila = {
            "mes": mes,
            "monto": round(monto, 2),
            "ajuste": False,
            "variacion_pct": None,
            "fuente": "inicial" if i == 0 else "sin ajuste",
            "nota": "",
        }

        es_ajuste = i > 0 and i % periodicidad_meses == 0
        if es_ajuste:
            if tipo == "FIJO":
                factor = 1.0 + porcentaje_fijo_pct / 100.0
                monto *= factor
                fila.update(ajuste=True, variacion_pct=porcentaje_fijo_pct, fuente="fijo")
            else:
                # Meses cuyas variaciones se encadenan en este ajuste
                ultimo = sumar_meses(mes, -rezago_meses)
                primero = sumar_meses(ultimo, -(periodicidad_meses - 1))
                meses_usados = [sumar_meses(primero, k) for k in range(periodicidad_meses)]

                valores: list[float] = []
                origenes: set[str] = set()
                faltantes: list[str] = []
                for m in meses_usados:
                    if m in reales:
                        valores.append(reales[m])
                        origenes.add("real")
                    elif m in proyectadas:
                        valores.append(proyectadas[m])
                        origenes.add("proyectado")
                    else:
                        faltantes.append(m)

                if faltantes:
                    fila.update(
                        fuente="sin dato",
                        nota=f"Falta la variación de {', '.join(faltantes)}; no se pudo ajustar.",
                    )
                else:
                    factor = factor_acumulado(valores)
                    monto *= factor
                    fuente = origenes.pop() if len(origenes) == 1 else "mixto"
                    fila.update(
                        ajuste=True,
                        variacion_pct=round((factor - 1.0) * 100.0, 4),
                        fuente=fuente,
                        nota=f"Usa {meses_usados[0]} a {meses_usados[-1]}.",
                    )
            fila["monto"] = round(monto, 2)

        filas.append(fila)

    return filas


# ---------------------------------------------------------------------------
# Proyección de inflación (REM del BCRA)
# ---------------------------------------------------------------------------

def proyectar_ipc_mensual(
    primer_mes: str | date,
    rem_mensual_pct: list[float],
    inflacion_12m_pct: float,
    meses: int = 12,
    ajuste_pp: float = 0.0,
) -> dict[str, float]:
    """Proyecta el IPC mensual (en %) a partir del REM del BCRA.

    * `rem_mensual_pct`: inflación mensual esperada por el REM para los primeros
      meses a proyectar, empezando en `primer_mes` (normalmente 6 valores).
    * `inflacion_12m_pct`: inflación esperada para los próximos 12 meses.
    * Los meses restantes hasta completar 12 se despejan de la expectativa a 12
      meses, repartiendo una tasa mensual constante r tal que:
          prod(1 + m_k) * (1 + r)^n_restantes = 1 + i12
    * `ajuste_pp`: puntos porcentuales que se suman a cada mes (escenario
      optimista < 0, pesimista > 0).

    Supuesto a verificar con la metodología del REM: la ventana de 12 meses
    comienza en `primer_mes`.
    """
    if not 1 <= meses <= 12:
        raise ValueError("meses debe estar entre 1 y 12.")
    rem = [float(x) for x in rem_mensual_pct][:12]
    inicio = normalizar_mes(primer_mes)

    restantes = 12 - len(rem)
    tasas = list(rem)
    if restantes > 0:
        base = (1.0 + inflacion_12m_pct / 100.0) / factor_acumulado(rem)
        if base <= 0:
            raise ValueError("La expectativa a 12 meses es inconsistente con los valores mensuales del REM.")
        r = (base ** (1.0 / restantes) - 1.0) * 100.0
        tasas += [r] * restantes

    return {
        sumar_meses(inicio, k): round(tasas[k] + ajuste_pp, 4)
        for k in range(meses)
    }


def proyectar_icl_mensual(
    ipc_proyectado_pct: Mapping[str, float],
    ripte_vs_ipc_pp: float = 0.0,
) -> dict[str, float]:
    """Aproxima la variación mensual del ICL (en %).

    El ICL promedia en partes iguales la variación del IPC y la del RIPTE
    (salarios). Si el RIPTE varía `ripte_vs_ipc_pp` puntos más que el IPC:
        ICL = IPC + ripte_vs_ipc_pp / 2
    Con 0 se asume salario real constante.
    """
    return {
        normalizar_mes(m): round(float(v) + ripte_vs_ipc_pp / 2.0, 4)
        for m, v in ipc_proyectado_pct.items()
    }
