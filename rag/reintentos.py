"""Reintentos con espera creciente para los límites de cuota (HTTP 429) de la API."""

from __future__ import annotations

import time


class LimiteDeCuota(RuntimeError):
    """La API respondió 429 / RESOURCE_EXHAUSTED y los reintentos no alcanzaron."""


def es_limite_de_cuota(exc: BaseException) -> bool:
    t = f"{type(exc).__name__} {exc}".lower()
    return "429" in t or "resource_exhausted" in t or "quota" in t or "rate limit" in t


def con_reintentos(fn, intentos: int = 4, espera: float = 2.0, dormir=time.sleep):
    """Ejecuta fn(); ante un 429 espera 2, 4, 8 s... y reintenta. Otros errores salen igual."""
    for n in range(intentos):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not es_limite_de_cuota(exc):
                raise
            if n == intentos - 1:
                raise LimiteDeCuota(
                    "Se alcanzó el límite de pedidos de la API (429) y los reintentos no alcanzaron."
                ) from exc
            dormir(espera * 2**n)
