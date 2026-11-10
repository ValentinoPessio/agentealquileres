"""Adaptador de proveedor de LLM.

El resto del proyecto solo llama a `get_model()` y `get_embeddings()`; cambiar de
proveedor se hace desde el .env (LLM_PROVIDER) sin tocar el agente.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Falta o es inválida alguna variable de configuración."""


def _requerida(nombre: str) -> str:
    valor = os.getenv(nombre, "").strip()
    if not valor:
        raise ConfigError(
            f"Falta la variable {nombre} en el .env (ver .env.example)."
        )
    return valor


def get_model(temperature: float = 0.2):
    """Devuelve el modelo de chat según LLM_PROVIDER (gemini | lmstudio)."""
    proveedor = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    reintentos = int(os.getenv("LLM_MAX_RETRIES", "2"))

    if proveedor == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # No se pasa `temperature`: los modelos Gemini 3.x usan muestreo fijo e
        # ignoran ese parámetro (avisan con un UserWarning).
        return ChatGoogleGenerativeAI(
            model=_requerida("GEMINI_MODEL"),
            google_api_key=_requerida("GOOGLE_API_KEY"),
            max_retries=reintentos,  # reintenta con espera ante errores transitorios / 429
            include_thoughts=True,   # pide los bloques de razonamiento (si el modelo los expone)
        )

    if proveedor == "lmstudio":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=_requerida("LMSTUDIO_MODEL"),
            base_url=os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
            api_key="lm-studio",  # LM Studio no valida la clave
            temperature=temperature,
            max_retries=reintentos,
        )

    raise ConfigError(f"LLM_PROVIDER='{proveedor}' no soportado (use gemini o lmstudio).")


def get_fallback_models() -> list:
    """Modelos de respaldo (GEMINI_FALLBACK_MODELS, separados por coma), en orden.

    El tier gratuito tiene una cuota diaria por modelo: cuando el principal responde 429
    por cuota agotada, reintentar no sirve, hay que pasar a otro modelo.
    """
    if os.getenv("LLM_PROVIDER", "gemini").strip().lower() != "gemini":
        return []
    nombres = [n.strip() for n in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if n.strip()]
    principal = os.getenv("GEMINI_MODEL", "").strip()
    nombres = [n for n in nombres if n != principal]
    if not nombres:
        return []
    from langchain_google_genai import ChatGoogleGenerativeAI

    clave = _requerida("GOOGLE_API_KEY")
    return [
        ChatGoogleGenerativeAI(model=n, google_api_key=clave, max_retries=1, include_thoughts=True)
        for n in nombres
    ]


def get_embeddings():
    """Devuelve el modelo de embeddings (Gemini)."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=f"models/{os.getenv('EMBEDDING_MODEL', 'gemini-embedding-001')}",
        google_api_key=_requerida("GOOGLE_API_KEY"),
    )
