from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from conversaciones import Almacen, historial_desde_mensajes


def test_registrar_y_listar_conserva_primer_titulo(tmp_path):
    a = Almacen(tmp_path / "c.sqlite")
    a.registrar("t1", "Primera consulta", "outputs/uploads/x.txt")
    a.registrar("t1", "Otra cosa", "outputs/uploads/x.txt")
    filas = a.listar()
    assert len(filas) == 1 and filas[0]["titulo"] == "Primera consulta"
    assert a.obtener("t1")["contrato_ruta"] == "outputs/uploads/x.txt"
    assert a.obtener("no-existe") is None


def test_persiste_entre_instancias(tmp_path):
    ruta = tmp_path / "c.sqlite"
    a = Almacen(ruta)
    a.registrar("t1", "Hola", None)
    a.cerrar()
    b = Almacen(ruta)
    assert [c["thread_id"] for c in b.listar()] == ["t1"]


def test_checkpointer_guarda_el_estado_del_agente(tmp_path):
    from agente import crear_agente
    from tests.test_agente import ModeloFalso  # modelo sin red

    ruta = tmp_path / "c.sqlite"
    a = Almacen(ruta)
    ag = crear_agente(modelo=ModeloFalso(messages=iter([AIMessage(content="Hola, soy el agente")])),
                      checkpointer=a.checkpointer)
    cfg = {"configurable": {"thread_id": "t1"}}
    ag.invoke({"messages": [{"role": "user", "content": "Hola"}]}, cfg)
    a.cerrar()
    # "reinicio": nueva conexión al mismo archivo
    b = Almacen(ruta)
    ag2 = crear_agente(modelo=ModeloFalso(messages=iter([])), checkpointer=b.checkpointer)
    msgs = ag2.get_state(cfg).values["messages"]
    assert [m.content for m in msgs] == ["Hola", "Hola, soy el agente"]


def test_historial_desde_mensajes_reconstruye_turnos_y_pasos():
    msgs = [
        HumanMessage("[Contrato adjunto: c.txt]\n\n¿Qué dice?"),
        AIMessage(content="", tool_calls=[{"name": "leer_contrato", "args": {}, "id": "1"}]),
        ToolMessage(content='{"clausulas": []}', name="leer_contrato", tool_call_id="1"),
        AIMessage(content="Dice esto."),
    ]
    h = historial_desde_mensajes(msgs)
    assert h[0] == {"rol": "user", "texto": "¿Qué dice?"}
    assert h[1]["rol"] == "assistant" and h[1]["texto"] == "Dice esto."
    assert any(p["tipo"] == "tool" for p in h[1]["pasos"])
