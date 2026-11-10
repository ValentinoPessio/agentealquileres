import pytest

import tools
from calculos import formatear_pesos, tabla_markdown, generar_cronograma


def test_formatear_pesos():
    assert formatear_pesos(432810.62) == "$ 432.810,62"
    assert formatear_pesos(400000) == "$ 400.000,00"


def test_tabla_markdown_tiene_cabecera_y_filas():
    filas = generar_cronograma(100_000, "2025-03", 4, 3, "FIJO", porcentaje_fijo_pct=10)
    tabla = tabla_markdown(filas)
    lineas = tabla.splitlines()
    assert lineas[0].startswith("| Mes |")
    assert len(lineas) == 2 + 4
    assert "$ 110.000,00" in lineas[-1]
    assert "10,00 %" in lineas[-1]


def test_calcular_cronograma_tool_ok():
    r = tools.calcular_cronograma.invoke(
        {
            "monto_inicial": 400000,
            "fecha_inicio": "2025-03",
            "meses_totales": 7,
            "periodicidad_meses": 3,
            "tipo_indice": "IPC",
            "variaciones_reales": [
                {"mes": "2025-03", "pct": 3.7},
                {"mes": "2025-04", "pct": 2.8},
                {"mes": "2025-05", "pct": 1.5},
            ],
            "variaciones_proyectadas": [
                {"mes": "2025-06", "pct": 2.0},
                {"mes": "2025-07", "pct": 2.0},
                {"mes": "2025-08", "pct": 2.0},
            ],
        }
    )
    assert "error" not in r
    assert r["cantidad_de_ajustes"] == 2
    assert r["monto_inicial"] == "$ 400.000,00"
    assert "$ 432.810,62" in r["tabla_markdown"]
    assert r["advertencias"] == []


def test_calcular_cronograma_tool_error_no_rompe():
    r = tools.calcular_cronograma.invoke(
        {
            "monto_inicial": -5,
            "fecha_inicio": "2025-03",
            "meses_totales": 4,
            "periodicidad_meses": 3,
            "tipo_indice": "IPC",
        }
    )
    assert "error" in r and "monto" in r["error"].lower()


def test_calcular_cronograma_avisa_datos_faltantes():
    r = tools.calcular_cronograma.invoke(
        {
            "monto_inicial": 100000,
            "fecha_inicio": "2025-03",
            "meses_totales": 4,
            "periodicidad_meses": 3,
            "tipo_indice": "IPC",
        }
    )
    assert r["cantidad_de_ajustes"] == 0
    assert len(r["advertencias"]) == 1


def test_proyectar_inflacion_tool():
    r = tools.proyectar_inflacion.invoke(
        {
            "primer_mes": "2026-11",
            "rem_mensual_pct": [2.0] * 6,
            "inflacion_12m_pct": 24.0,
        }
    )
    assert len(r["variaciones_proyectadas"]) == 12
    assert r["variaciones_proyectadas"][0] == {"mes": "2026-11", "pct": 2.0}
    assert r["acumulado_pct"] == pytest.approx(24.0, abs=0.1)

    pes = tools.proyectar_inflacion.invoke(
        {
            "primer_mes": "2026-11",
            "rem_mensual_pct": [2.0] * 6,
            "inflacion_12m_pct": 24.0,
            "escenario": "pesimista",
        }
    )
    assert pes["variaciones_proyectadas"][0]["pct"] == pytest.approx(2.3)


def test_proyectar_inflacion_error_claro():
    r = tools.proyectar_inflacion.invoke(
        {"primer_mes": "2026-11", "rem_mensual_pct": [2.0] * 6, "inflacion_12m_pct": -100.0}
    )
    assert "error" in r


def test_leer_contrato_lee_dentro_de_carpeta_permitida(tmp_path, monkeypatch):
    carpeta = tmp_path / "uploads"
    carpeta.mkdir()
    (carpeta / "c.txt").write_text("PRIMERA: OBJETO. Casa.\nSEGUNDA: PRECIO. $1.000.", encoding="utf-8")
    monkeypatch.setattr(tools, "CARPETAS_PERMITIDAS", (carpeta,))
    r = tools.leer_contrato.invoke({"ruta": str(carpeta / "c.txt")})
    assert "error" not in r
    assert len(r["clausulas"]) == 2


def test_leer_contrato_rechaza_rutas_fuera_de_la_carpeta(tmp_path, monkeypatch):
    carpeta = tmp_path / "uploads"
    carpeta.mkdir()
    secreto = tmp_path / "secreto.txt"
    secreto.write_text("clave")
    monkeypatch.setattr(tools, "CARPETAS_PERMITIDAS", (carpeta,))
    # ruta absoluta fuera
    assert "error" in tools.leer_contrato.invoke({"ruta": str(secreto)})
    # path traversal
    assert "error" in tools.leer_contrato.invoke({"ruta": str(carpeta / ".." / "secreto.txt")})
    # el .env del proyecto
    assert "error" in tools.leer_contrato.invoke({"ruta": ".env"})


def test_leer_contrato_archivo_inexistente_no_rompe(tmp_path, monkeypatch):
    carpeta = tmp_path / "uploads"
    carpeta.mkdir()
    monkeypatch.setattr(tools, "CARPETAS_PERMITIDAS", (carpeta,))
    r = tools.leer_contrato.invoke({"ruta": str(carpeta / "no_existe.pdf")})
    assert "error" in r


def test_nombres_y_descripciones_de_las_tools():
    nombres = [t.name for t in tools.TOOLS]
    assert nombres == ["leer_contrato", "calcular_cronograma", "proyectar_inflacion"]
    for t in tools.TOOLS:
        assert t.description and len(t.description) > 40
