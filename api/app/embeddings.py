"""Vector de la pregunta del buscador, con el mismo modelo que los trozos (bge-m3 en Ollama).

Para qué: para buscar por significado, la pregunta se convierte en un vector del mismo modelo y
tamaño (1024) que los trozos que guardó el indexador; si no coinciden, no se pueden comparar.

Por qué está duplicado con indexador/embeddings.py (unas líneas): la API y el indexador son
contenedores independientes y compartir código obligaría a un paquete común. Cambiar de modelo =
cambiar los dos ficheros, con la misma firma, y revectorizar.

Errores: `OllamaNoDisponible` si no responde (túnel cerrado, servidor caído → 503 en el buscador)
y `EmbeddingsError` si responde con error (modelo no descargado… → 502 con su mensaje).

Quién lo usa: routers/busqueda.py.
"""

import httpx

DIMENSIONES = 1024
TIEMPO_MAX_S = 60  # una pregunta tarda ~0,2 s; la primera tras un rato, unos segundos más (cargar el modelo)


class EmbeddingsError(Exception):
    """Ollama respondió con un error o con un vector que no sirve."""


class OllamaNoDisponible(EmbeddingsError):
    """Ollama no responde."""


def vectorizar_pregunta(texto: str, url: str, modelo: str, cliente: httpx.Client | None = None) -> list[float]:
    """Vector de 1024 números de `texto`. `cliente` solo se pasa en los tests."""
    if cliente is None:
        with httpx.Client(timeout=TIEMPO_MAX_S) as propio:  # se cierra al terminar: una conexión por pregunta
            return vectorizar_pregunta(texto, url, modelo, propio)
    try:
        r = cliente.post(f"{url}/api/embed", json={"model": modelo, "input": [texto]})
    except httpx.HTTPError as e:
        raise OllamaNoDisponible(f"Ollama no responde en {url} ({type(e).__name__})") from None
    if r.status_code != 200:
        try:
            motivo = r.json().get("error") or r.text[:300]
        except ValueError:
            motivo = r.text[:300]
        raise EmbeddingsError(f"Ollama respondió {r.status_code}: {motivo}")
    vectores = r.json().get("embeddings") or [[]]
    if len(vectores[0]) != DIMENSIONES:
        raise EmbeddingsError(f"El modelo «{modelo}» da vectores de {len(vectores[0])} dimensiones "
                              f"y los trozos tienen {DIMENSIONES}")
    return vectores[0]
