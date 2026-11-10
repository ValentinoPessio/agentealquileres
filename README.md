# Agente revisor de contratos de alquiler

Proyecto integrador - Modelos de Lenguaje (UTN FRM, 2026).

Agente de IA (LangChain, `create_agent`) que recibe un contrato de alquiler en
PDF o TXT, extrae sus cláusulas, las contrasta con la normativa y calcula la
actualización del alquiler según el índice pactado (IPC, ICL o porcentaje fijo),
incluyendo una proyección a 6-12 meses.

> Estado: en desarrollo. Esta sección se completa a medida que avanza el proyecto.

> El agente es una ayuda para entender un contrato. **No reemplaza a un abogado.**

## Instalación

```bash
git clone https://github.com/ValentinoPessio/agentealquileres
cd agentealquileres
python -m venv .venv
# Windows: .venv\Scripts\activate    |   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # Windows: copy .env.example .env
```

Completar en `.env` la `GOOGLE_API_KEY` (gratis en https://aistudio.google.com) y
el `GEMINI_MODEL`.

## Verificar el proveedor de LLM

```bash
python scripts/probar_modelo.py
```

Comprueba tres cosas: que el modelo llama a una tool, si devuelve bloques de
razonamiento, y que la memoria de corto plazo funciona entre turnos.

## Ejecutar la app

```bash
streamlit run app.py
```

Subí un contrato (PDF o TXT con texto seleccionable) desde la barra lateral y
escribí tu consulta. La UI muestra, mientras el agente trabaja, cada tool
invocada con sus argumentos, su resultado y el razonamiento del modelo (si el
proveedor lo expone), y después la respuesta final en markdown. La memoria de
corto plazo es por conversación; "Nueva conversación" la reinicia.

## Construir el índice de normativa (RAG)

Los textos legales (CCyC locación y cláusulas abusivas, DNU 70/2023, Ley 24.240) están
en `data/normativa/*.md`, un artículo por bloque `## Art. N`. Se generaron con
`scripts/extraer_normativa.py` a partir de las páginas de InfoLEG (reproducible: guardar las
páginas en `data/normativa/fuentes/` y correr el script). Para indexarlos:

```bash
python -m rag.ingest
```

Crea `chroma_db/` (ignorado por git) con un fragmento por artículo. Hay que correrlo una vez
antes de usar la app.

## Tests

```bash
pytest
```

Los tests no llaman a Gemini: el agente se prueba con un modelo simulado.

## Estructura

```
app.py              UI en Streamlit (streaming de pasos, memoria por conversación)
agente.py           create_agent + prompt de sistema + checkpointer
flujo.py            convierte los mensajes del agente en pasos para la UI
model.py            adaptador de proveedor LLM
tools.py            tools del agente (leer_contrato, calcular_cronograma, proyectar_inflacion)
calculos.py         lógica pura de cálculo (cronograma, proyección)
contratos.py        lectura de PDF/TXT y división en cláusulas
rag/                ingesta (rag/ingest.py) y búsqueda (rag/buscar.py) de la normativa
data/normativa/     textos legales para el RAG
data/contratos_ejemplo/   contratos ficticios para pruebas
scripts/            utilidades
tests/              tests
```
