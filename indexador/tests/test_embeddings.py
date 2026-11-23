"""Tests de embeddings.py con un Ollama simulado (httpx.MockTransport).

Las respuestas imitan las de `POST /api/embed` de Ollama 0.40 con bge-m3 (1024 dimensiones).
"""

import json

import httpx
import pytest
from embeddings import DIMENSIONES, EmbeddingsError, vectorizar

URL = "http://ollama:11434"


def vector(i: float) -> list[float]:
    return [i] * DIMENSIONES


def ollama(peticiones: list, codigo: int = 200, cuerpo: dict | None = None) -> httpx.Client:
    """Cliente que responde como Ollama: un vector por texto, cuyo valor es el número del texto."""

    def responder(request: httpx.Request) -> httpx.Response:
        datos = json.loads(request.content)
        peticiones.append((request.url.path, datos))
        if cuerpo is not None or codigo != 200:
            return httpx.Response(codigo, json=cuerpo or {})
        return httpx.Response(200, json={"model": datos["model"],
                                         "embeddings": [vector(float(t)) for t in datos["input"]]})

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_va_en_lotes_y_conserva_el_orden():
    peticiones = []
    textos = [str(i) for i in range(40)]
    vectores = vectorizar(textos, URL, cliente=ollama(peticiones))
    assert [len(p[1]["input"]) for p in peticiones] == [16, 16, 8]
    assert all(p[0] == "/api/embed" and p[1]["model"] == "bge-m3" for p in peticiones)
    assert [v[0] for v in vectores] == [float(i) for i in range(40)]


def test_usa_el_modelo_indicado():
    peticiones = []
    vectorizar(["1"], URL, modelo="otro-de-1024", cliente=ollama(peticiones))
    assert peticiones[0][1]["model"] == "otro-de-1024"


def test_lista_vacia_no_llama_a_ollama():
    peticiones = []
    assert vectorizar([], URL, cliente=ollama(peticiones)) == []
    assert peticiones == []


def test_modelo_no_descargado_da_error_con_el_motivo():
    cliente = ollama([], codigo=404, cuerpo={"error": "model \"bge-m3\" not found, try pulling it first"})
    with pytest.raises(EmbeddingsError, match="Ollama respondió 404: model \"bge-m3\" not found"):
        vectorizar(["1"], URL, cliente=cliente)


def test_ollama_caido_da_error_claro():
    def caido(request):
        raise httpx.ConnectError("Connection refused")

    with pytest.raises(EmbeddingsError, match=f"Ollama no responde en {URL}"):
        vectorizar(["1"], URL, cliente=httpx.Client(transport=httpx.MockTransport(caido)))


def test_vectores_de_otro_tamano_dan_error():
    # La columna es halfvec(1024): con otro modelo fallaría al guardar, mejor avisar aquí.
    cliente = ollama([], cuerpo={"embeddings": [[0.1] * 768]})
    with pytest.raises(EmbeddingsError, match="768 dimensiones"):
        vectorizar(["1"], URL, cliente=cliente)


def test_respuesta_con_menos_vectores_que_textos_da_error():
    cliente = ollama([], cuerpo={"embeddings": [vector(1.0)]})
    with pytest.raises(EmbeddingsError, match="1 vectores para 2 textos"):
        vectorizar(["1", "2"], URL, cliente=cliente)
