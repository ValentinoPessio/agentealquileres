"""Pruebas del generador de índices con archivos fuente sintéticos."""

import importlib.util
import sys
from pathlib import Path

import openpyxl
import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "generar_indices.py"
spec = importlib.util.spec_from_file_location("generar_indices", RUTA)
gi = importlib.util.module_from_spec(spec)
sys.modules["generar_indices"] = gi
spec.loader.exec_module(gi)

CABECERA = "Codigo;Descripcion;Clasificador;Periodo;Indice_IPC;v_m_IPC;v_i_a_IPC;Region\n"


def _csv_ipc(tmp_path, filas):
    ruta = tmp_path / "serie_ipc_divisiones.csv"
    ruta.write_text(CABECERA + "".join(filas), encoding="latin-1")
    return ruta


def test_leer_ipc_calcula_variaciones_y_filtra_nacional(tmp_path):
    ruta = _csv_ipc(
        tmp_path,
        [
            "0;NIVEL GENERAL;x;202601;100;NA;NA;Nacional\n",
            "0;NIVEL GENERAL;x;202602;102,5;2,5;NA;Nacional\n",
            "0;NIVEL GENERAL;x;202602;999;9,9;NA;GBA\n",
            "01;Alimentos;x;202602;200;8;NA;Nacional\n",
        ],
    )
    r = gi.leer_ipc(ruta)
    assert r["variaciones_mensuales_pct"] == {"2026-02": 2.5}
    assert r["ultimo_mes"] == "2026-02"


def test_leer_ipc_detecta_inconsistencia_con_la_variacion_publicada(tmp_path):
    ruta = _csv_ipc(
        tmp_path,
        ["0;N;x;202601;100;NA;NA;Nacional\n", "0;N;x;202602;110;2,5;NA;Nacional\n"],
    )
    with pytest.raises(AssertionError):
        gi.leer_ipc(ruta)


def test_leer_icl_toma_el_nivel_del_dia_1(tmp_path):
    ruta = tmp_path / "icl.csv"
    ruta.write_text("﻿Fecha,Valor\n2026-10-01,36.54\n2026-10-02,36.56\n2026-11-01,37.21\n2026-11-02,37.23\n", encoding="utf-8")
    r = gi.leer_icl(ruta)
    assert r["niveles_dia_1"] == {"2026-10": 36.54, "2026-11": 37.21}
    assert r["ultimo_dato"] == "2026-11-02"


def test_leer_rem_lee_mensuales_y_expectativa_a_12_meses(tmp_path):
    from datetime import datetime

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cuadros de resultados"
    ws.cell(2, 2, "Relevamiento de Expectativas de Mercado (REM)  - BCRA - Octubre 2026")
    ws.cell(5, 2, "Precios minoristas (IPC nivel general-Nacional; INDEC)")
    ws.cell(7, 2, datetime(2026, 10, 31)); ws.cell(7, 3, "var. % mensual"); ws.cell(7, 4, 1.8)
    ws.cell(8, 2, datetime(2026, 11, 30)); ws.cell(8, 3, "var. % mensual"); ws.cell(8, 4, 1.7)
    filas = [("próx. 12 meses", "var. % i.a.; oct-27", 21.8), ("próx. 24 meses", "var. % i.a.; oct-28", 17.3),
             ("2026", "var. % i.a.; dic-26", 30.36), ("2027", "var. % i.a.; dic-27", 21.9), ("2028", "var. % i.a.; dic-28", 15.3)]
    for i, (a, b, c) in enumerate(filas, start=9):
        ws.cell(i, 2, a); ws.cell(i, 3, b); ws.cell(i, 4, c)
    ruta = tmp_path / "rem.xlsx"
    wb.save(ruta)
    r = gi.leer_rem(ruta)
    assert r["relevamiento"] == "2026-10"
    assert r["mensual_mediana_pct"] == {"2026-10": 1.8, "2026-11": 1.7}
    assert r["proximos_12_meses_pct"] == 21.8
