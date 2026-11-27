"""Embeddings de los trozos con un modelo local en Ollama (bge-m3, 1024 dimensiones).

Para qué: convierte el texto de cada trozo en un vector, que se guarda en `fragmentos.embedding`
para buscar por significado.

Por qué Ollama y bge-m3: los documentos no salen de nuestros equipos (sin API externa ni clave de
pago), bge-m3 entiende español y textos largos, y da 1024 dimensiones, el tamaño de la columna
`halfvec(1024)`. Ollama corre en el servidor de la universidad; en desarrollo se llega por un
túnel SSH (`OLLAMA_URL`, ver README).

Lotes de 16 textos: sin GPU bge-m3 tarda ~1,6 s por trozo (medido en el servidor), así que cada
petición dura ~25 s y no roza el tiempo máximo. Si Ollama no responde o falta el modelo, se lanza
EmbeddingsError: el documento queda reintentable y luego en «error» con el motivo.

Cambiar de proveedor = cambiar este fichero (y el de la API, con la misma firma) y revectorizar.

Quién lo usa: procesar.py.
"""

import httpx

DIMENSIONES = 1024
MODELO = "bge-m3"
LOTE = 16
TIEMPO_MAX_S = 300


class EmbeddingsError(Exception):
    """Ollama no responde, falta el modelo o devuelve vectores que no encajan en la tabla."""


def vectorizar(textos: list[str], url: str, modelo: str = MODELO,
               cliente: httpx.Client | None = None) -> list[list[float]]:
    """Un vector de 1024 números por texto, en el mismo orden. `cliente` solo se pasa en los tests.

    Raises:
        EmbeddingsError: con un motivo legible, que acaba en `indexado.error`.
    """
    if not textos:
        return []
    if cliente is None:
        with httpx.Client(timeout=TIEMPO_MAX_S) as propio:  # se cierra al terminar el documento
            return vectorizar(textos, url, modelo, propio)
    vectores: list[list[float]] = []
    for i in range(0, len(textos), LOTE):
        lote = textos[i:i + LOTE]
        try:
            r = cliente.post(f"{url}/api/embed", json={"model": modelo, "input": lote})
        except httpx.HTTPError as e:
            raise EmbeddingsError(f"Ollama no responde en {url} ({type(e).__name__})") from None
        if r.status_code != 200:
            raise EmbeddingsError(f"Ollama respondió {r.status_code}: {_motivo(r)}")
        recibidos = r.json().get("embeddings") or []
        if len(recibidos) != len(lote):
            raise EmbeddingsError(f"Ollama devolvió {len(recibidos)} vectores para {len(lote)} textos")
        if any(len(v) != DIMENSIONES for v in recibidos):
            raise EmbeddingsError(f"El modelo «{modelo}» da vectores de {len(recibidos[0])} dimensiones "
                                  f"y la tabla espera {DIMENSIONES}")
        vectores.extend(recibidos)
    return vectores


def _motivo(r: httpx.Response) -> str:
    """El campo `error` de Ollama si lo trae; si no, el principio del cuerpo."""
    try:
        return str(r.json().get("error") or r.text[:300])
    except ValueError:
        return r.text[:300]
