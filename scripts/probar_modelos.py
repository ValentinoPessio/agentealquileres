"""Prueba varios modelos de Gemini por API, con corte corto, y dice cuáles responden.

Uso (con el .env completo):
    python scripts/probar_modelos.py            # prueba los modelos 'flash' que ve tu clave
    python scripts/probar_modelos.py nombre1 nombre2   # prueba solo esos nombres

Imprime OK / FALLÓ por modelo. Los que dicen OK sirven para GEMINI_MODEL.
"""

from __future__ import annotations

import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

TIMEOUT_MS = 30_000
MAX_MODELOS = 10
EXCLUIR = ("image", "tts", "live", "embedding", "audio", "veo", "imagen", "robotics", "computer-use")


def modelos_candidatos(cliente) -> list[str]:
    nombres: list[str] = []
    for m in cliente.models.list():
        nombre = m.name.removeprefix("models/")
        if "gemini" not in nombre or "flash" not in nombre:
            continue
        if any(x in nombre for x in EXCLUIR):
            continue
        acciones = getattr(m, "supported_actions", None)
        if acciones is not None and "generateContent" not in acciones:
            continue
        nombres.append(nombre)
    return sorted(set(nombres))[:MAX_MODELOS]


def main() -> int:
    clave = os.getenv("GOOGLE_API_KEY", "").strip()
    if not clave:
        print("Falta GOOGLE_API_KEY en el .env")
        return 1

    cliente = genai.Client(
        api_key=clave,
        http_options=types.HttpOptions(timeout=TIMEOUT_MS),
    )

    nombres = [n.removeprefix("models/") for n in sys.argv[1:]] or modelos_candidatos(cliente)
    if not nombres:
        print("No se encontraron modelos para probar.")
        return 1

    print(f"Probando {len(nombres)} modelo(s), corte de {TIMEOUT_MS // 1000} s cada uno:\n")
    for nombre in nombres:
        inicio = time.time()
        try:
            r = cliente.models.generate_content(model=nombre, contents="Decí hola en una palabra.")
            texto = (r.text or "").strip().replace("\n", " ")[:40]
            print(f"  OK     {nombre:40s} {time.time() - inicio:5.1f} s  -> {texto}")
        except Exception as exc:  # noqa: BLE001 - script de diagnóstico
            motivo = str(exc).replace("\n", " ")[:90]
            print(f"  FALLÓ  {nombre:40s} {time.time() - inicio:5.1f} s  {type(exc).__name__}: {motivo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
