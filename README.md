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

## Tests

```bash
pytest
```

## Estructura

```
app.py              UI en Streamlit (pendiente)
agente.py           create_agent + prompt de sistema (pendiente)
model.py            adaptador de proveedor LLM
tools.py            tools del agente (pendiente)
calculos.py         lógica pura de cálculo (cronograma, proyección)
contratos.py        lectura de PDF/TXT y división en cláusulas
rag/                ingesta y base vectorial (pendiente)
data/normativa/     textos legales para el RAG
data/contratos_ejemplo/   contratos ficticios para pruebas
scripts/            utilidades
tests/              tests
```
