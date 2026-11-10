import pytest

from calculos import (
    factor_acumulado,
    generar_cronograma,
    normalizar_mes,
    proyectar_icl_mensual,
    proyectar_ipc_mensual,
    sumar_meses,
    variaciones_desde_niveles,
)


def test_normalizar_y_sumar_meses():
    assert normalizar_mes("2025-03-15") == "2025-03"
    assert sumar_meses("2025-11", 3) == "2026-02"
    assert sumar_meses("2025-01", -1) == "2024-12"
    with pytest.raises(ValueError):
        normalizar_mes("marzo 2025")


def test_factor_acumulado():
    # 10 % y 10 % -> 21 %
    assert factor_acumulado([10, 10]) == pytest.approx(1.21)


def test_ajuste_fijo_a_mano():
    # 400.000, +5 % cada 3 meses: jun = 420.000, sep = 441.000
    filas = generar_cronograma(
        monto_inicial=400_000,
        fecha_inicio="2025-03",
        meses_totales=7,
        periodicidad_meses=3,
        tipo_indice="FIJO",
        porcentaje_fijo_pct=5,
    )
    montos = {f["mes"]: f["monto"] for f in filas}
    assert montos["2025-03"] == 400_000
    assert montos["2025-05"] == 400_000
    assert montos["2025-06"] == 420_000
    assert montos["2025-08"] == 420_000
    assert montos["2025-09"] == 441_000
    assert [f["ajuste"] for f in filas] == [False, False, False, True, False, False, True]


def test_ajuste_ipc_trimestral_a_mano():
    # Inicio mar-2025, ajuste trimestral, rezago 1.
    # Junio usa mar, abr, may: 1,037 * 1,028 * 1,015 = 1,08202654
    #   400.000 * 1,08202654 = 432.810,62
    # Septiembre usa jun, jul, ago (proyectados 2 % c/u): 1,02^3 = 1,061208
    reales = {"2025-03": 3.7, "2025-04": 2.8, "2025-05": 1.5}
    proy = {"2025-06": 2.0, "2025-07": 2.0, "2025-08": 2.0}
    filas = generar_cronograma(
        monto_inicial=400_000,
        fecha_inicio="2025-03",
        meses_totales=7,
        periodicidad_meses=3,
        tipo_indice="IPC",
        variaciones_reales_pct=reales,
        variaciones_proyectadas_pct=proy,
    )
    por_mes = {f["mes"]: f for f in filas}
    assert por_mes["2025-06"]["monto"] == pytest.approx(432_810.62, abs=0.01)
    assert por_mes["2025-06"]["fuente"] == "real"
    assert por_mes["2025-06"]["variacion_pct"] == pytest.approx(8.2027, abs=1e-3)
    esperado_sep = 400_000 * 1.08202654 * 1.02**3
    assert por_mes["2025-09"]["monto"] == pytest.approx(esperado_sep, abs=0.05)
    assert por_mes["2025-09"]["fuente"] == "proyectado"


def test_fuente_mixta_y_prioridad_de_reales():
    reales = {"2025-03": 3.0, "2025-04": 3.0}
    proy = {"2025-04": 99.0, "2025-05": 3.0}  # abril ya es real: se ignora el proyectado
    filas = generar_cronograma(
        100_000, "2025-03", 4, 3, "IPC",
        variaciones_reales_pct=reales, variaciones_proyectadas_pct=proy,
    )
    jun = filas[3]
    assert jun["fuente"] == "mixto"
    assert jun["monto"] == pytest.approx(100_000 * 1.03**3, abs=0.01)


def test_falta_dato_no_rompe_el_flujo():
    filas = generar_cronograma(
        100_000, "2025-03", 4, 3, "IPC",
        variaciones_reales_pct={"2025-03": 3.0},
    )
    jun = filas[3]
    assert jun["fuente"] == "sin dato"
    assert jun["ajuste"] is False
    assert jun["monto"] == 100_000
    assert "2025-04" in jun["nota"]


def test_validaciones():
    with pytest.raises(ValueError):
        generar_cronograma(0, "2025-03", 4, 3, "IPC")
    with pytest.raises(ValueError):
        generar_cronograma(100, "2025-03", 4, 3, "DOLAR")
    with pytest.raises(ValueError):
        generar_cronograma(100, "2025-03", 4, 3, "FIJO")  # falta porcentaje
    with pytest.raises(ValueError):
        generar_cronograma(100, "2025-03", 4, 0, "IPC")


def test_variaciones_desde_niveles_icl():
    niveles = {"2026-08": 35.01, "2026-09": 35.71, "2026-10": 36.54}
    var = variaciones_desde_niveles(niveles)
    assert var["2026-08"] == pytest.approx((35.71 / 35.01 - 1) * 100)
    assert var["2026-09"] == pytest.approx((36.54 / 35.71 - 1) * 100)
    assert "2026-10" not in var  # no hay nivel de noviembre


def test_icl_equivale_a_cociente_de_niveles():
    # Ajuste trimestral por ICL: monto * ICL(1 de mes M) / ICL(1 de mes M-3)
    niveles = {"2025-03": 20.0, "2025-04": 20.5, "2025-05": 21.0, "2025-06": 21.8}
    var = variaciones_desde_niveles(niveles)
    filas = generar_cronograma(
        100_000, "2025-03", 4, 3, "ICL", variaciones_reales_pct=var
    )
    assert filas[3]["monto"] == pytest.approx(100_000 * 21.8 / 20.0, abs=0.01)


def test_proyeccion_ipc_despeja_los_meses_restantes():
    # 6 meses al 2 % + resto a r tal que (1,02^6)*(1+r)^6 = 1,24
    rem = [2.0] * 6
    proy = proyectar_ipc_mensual("2026-11", rem, inflacion_12m_pct=24.0, meses=12)
    assert list(proy)[0] == "2026-11"
    assert list(proy)[-1] == "2027-10"
    assert proy["2026-11"] == 2.0
    r = proy["2027-05"]
    assert r == pytest.approx(1.618, abs=0.01)
    # Los 12 meses encadenados deben dar la expectativa a 12 meses
    assert factor_acumulado(proy.values()) == pytest.approx(1.24, abs=1e-3)


def test_proyeccion_con_escenario():
    base = proyectar_ipc_mensual("2026-11", [2.0] * 6, 24.0, meses=6)
    pes = proyectar_ipc_mensual("2026-11", [2.0] * 6, 24.0, meses=6, ajuste_pp=0.3)
    assert pes["2026-11"] == pytest.approx(base["2026-11"] + 0.3)


def test_proyeccion_inconsistente_falla_claro():
    with pytest.raises(ValueError):
        proyectar_ipc_mensual("2026-11", [2.0] * 6, -100.0)


def test_proyeccion_icl_desde_ipc():
    ipc = {"2026-11": 2.0, "2026-12": 1.8}
    assert proyectar_icl_mensual(ipc) == {"2026-11": 2.0, "2026-12": 1.8}
    assert proyectar_icl_mensual(ipc, ripte_vs_ipc_pp=1.0)["2026-11"] == pytest.approx(2.5)
