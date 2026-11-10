"""Llamada mínima a Gemini SIN LangChain, para aislar problemas.

Sirve para distinguir si un error (por ejemplo 503) viene del servicio de Google
o de cómo se llama al modelo desde LangChain.

Uso (con el .env completo):
    python scripts/probar_api_directa.py
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

clave = os.getenv("GOOGLE_API_KEY", "").strip()
modelo = os.getenv("GEMINI_MODEL", "").strip()

if not clave or not modelo:
    raise SystemExit("Falta GOOGLE_API_KEY o GEMINI_MODEL en el .env")

print(f"Modelo: {modelo}")
cliente = genai.Client(api_key=clave)

inicio = time.time()
try:
    respuesta = cliente.models.generate_content(
        model=modelo,
        contents="Decime hola en una frase.",
    )
except Exception as exc:  # noqa: BLE001 - script de diagnóstico
    print(f"FALLÓ tras {time.time() - inicio:.1f} s: {type(exc).__name__}: {exc}")
    raise SystemExit(1)

print(f"OK en {time.time() - inicio:.1f} s")
print(respuesta.text)
