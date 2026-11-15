"""Mide si el RAG encuentra el artículo correcto (hit@k) con embeddings reales de Gemini.

Uso:  python -m scripts.evaluar_rag          (necesita GOOGLE_API_KEY y el índice construido)

Cada caso es una pregunta y el/los artículos que deberían aparecer en los primeros k resultados.
Sirve para decidir con números si hay que cambiar el tamaño de los fragmentos o el k, y para
mostrar en la defensa cómo se evaluó la recuperación.
"""

from __future__ import annotations

from rag.buscar import buscar_varias

# (pregunta, {(parte del nombre de la norma, artículo)} cualquiera de los cuales cuenta como acierto).
# El DNU 70/2023 sustituye artículos del CCyC y trae su texto vigente, por eso a veces se aceptan ambos.
CASOS = [
    ("rescisión anticipada del inquilino y penalidad", {("Código Civil", "1221"), ("Decreto", "262")}),
    ("garantía y depósito que pide el locador", {("Código Civil", "1196"), ("Decreto", "255")}),
    ("el locador entra al inmueble sin avisar", {("Código Civil", "1201")}),
    ("actualización del alquiler por índice o moneda de pago", {("Código Civil", "1199"), ("Decreto", "257")}),
    ("plazo mínimo del contrato de locación de vivienda", {("Código Civil", "1198"), ("Decreto", "256")}),
    ("cláusula abusiva en contrato de adhesión", {("Código Civil", "988"), ("Ley 24.240", "37")}),
    ("el inquilino puede subalquilar o ceder el contrato", {("Código Civil", "1213"), ("Código Civil", "1214")}),
    ("devolución del inmueble al terminar el contrato", {("Código Civil", "1210")}),
    ("quién paga las mejoras que hace el inquilino", {("Código Civil", "1211")}),
    ("incumplimiento de pago y desalojo", {("Código Civil", "1219"), ("Código Civil", "1222"), ("Decreto", "260")}),
]


def evaluar(k: int = 4) -> float:
    aciertos = 0
    for pregunta, esperados in CASOS:
        r = buscar_varias([pregunta], k=k)
        obtenidos = [(x["norma"], x["articulo"]) for x in r]
        ok = any(e_norma in norma and e_art == art for norma, art in obtenidos for e_norma, e_art in esperados)
        aciertos += ok
        print(("OK    " if ok else "FALLA "), pregunta, "->", [f"{n[:10]} {a}" for n, a in obtenidos])
    print(f"\nhit@{k}: {aciertos}/{len(CASOS)}")
    return aciertos / len(CASOS)


if __name__ == "__main__":
    evaluar()
