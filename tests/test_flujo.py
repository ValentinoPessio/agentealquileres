from langchain_core.messages import AIMessage, ToolMessage

from flujo import extraer_partes, pasos_de_mensaje, resumir


def test_extraer_partes_texto_simple():
    assert extraer_partes(AIMessage(content="hola")) == ("", "hola")


def test_extraer_partes_bloques_gemini():
    msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Primero leo el contrato."},
            {"type": "text", "text": "Listo."},
        ]
    )
    assert extraer_partes(msg) == ("Primero leo el contrato.", "Listo.")


def test_extraer_partes_bloques_estandar_reasoning():
    msg = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "Pienso."},
            {"type": "text", "text": "Respuesta."},
        ]
    )
    assert extraer_partes(msg) == ("Pienso.", "Respuesta.")


def test_sin_razonamiento_devuelve_vacio():
    msg = AIMessage(content=[{"type": "text", "text": "solo texto"}])
    assert extraer_partes(msg) == ("", "solo texto")


def test_pasos_con_tool_call_no_es_respuesta_final():
    msg = AIMessage(
        content=[{"type": "thinking", "thinking": "Voy a leer."}],
        tool_calls=[{"name": "leer_contrato", "args": {"ruta": "x.pdf"}, "id": "1", "type": "tool_call"}],
    )
    pasos, final = pasos_de_mensaje(msg)
    assert final == ""
    assert [p["tipo"] for p in pasos] == ["razonamiento", "tool"]
    assert pasos[1]["nombre"] == "leer_contrato"
    assert pasos[1]["args"] == {"ruta": "x.pdf"}


def test_pasos_respuesta_final():
    msg = AIMessage(content=[{"type": "text", "text": "Todo bien."}])
    pasos, final = pasos_de_mensaje(msg)
    assert pasos == []
    assert final == "Todo bien."


def test_pasos_de_tool_message():
    msg = ToolMessage(content='{"ok": true}', name="calcular_cronograma", tool_call_id="1")
    pasos, final = pasos_de_mensaje(msg)
    assert final == ""
    assert pasos == [
        {"tipo": "resultado", "nombre": "calcular_cronograma", "texto": '{"ok": true}', "error": False}
    ]


def test_tool_message_con_error_se_marca():
    msg = ToolMessage(content="boom", name="x", tool_call_id="1", status="error")
    pasos, _ = pasos_de_mensaje(msg)
    assert pasos[0]["error"] is True


def test_resumir_recorta_resultados_largos():
    largo = "a" * 2000
    r = resumir(largo, 100)
    assert r.startswith("a" * 100)
    assert "1900 caracteres más" in r
