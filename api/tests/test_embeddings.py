"""Tests de app/embeddings.py con un Ollama simulado (httpx.MockTransport).

Mismo modelo y dimensiones que el indexador: si no coinciden, la pregunta no se puede comparar
con los trozos guardados.
"""

import httpx
import pytest

from app.embeddings import DIMENSIONES, EmbeddingsError, OllamaNoDisponible, vectorizar_pregunta

URL = "http://ollama:11434"


def ollama(codigo=200, cuerpo=None, peticiones=None):
    def responder(request):
        if peticiones is not None:
            peticiones.append((request.url.path, request.read()))
        return httpx.Response(codigo, json=cuerpo if cuerpo is not None else {"embeddings": [[0.5] * DIMENSIONES]})

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_devuelve_el_vector_de_la_pregunta():
    peticiones = []
    v = vectorizar_pregunta("¿Cuánto cuesta?", URL, "bge-m3", cliente=ollama(peticiones=peticiones))
    assert v == [0.5] * DIMENSIONES
    assert peticiones[0][0] == "/api/embed"
    assert b'"model":"bge-m3"' in peticiones[0][1].replace(b" ", b"")


def test_ollama_caido_es_ollama_no_disponible():
    def caido(request):
        raise httpx.ConnectError("Connection refused")

    with pytest.raises(OllamaNoDisponible, match=f"Ollama no responde en {URL}"):
        vectorizar_pregunta("x", URL, "bge-m3", cliente=httpx.Client(transport=httpx.MockTransport(caido)))


def test_error_de_ollama_lleva_su_mensaje_y_no_es_no_disponible():
    cliente = ollama(404, {"error": "model 'bge-m3' not found"})
    with pytest.raises(EmbeddingsError, match="Ollama respondió 404: model 'bge-m3' not found") as e:
        vectorizar_pregunta("x", URL, "bge-m3", cliente=cliente)
    assert not isinstance(e.value, OllamaNoDisponible)


def test_vector_de_otro_tamano_es_error():
    with pytest.raises(EmbeddingsError, match="768 dimensiones"):
        vectorizar_pregunta("x", URL, "otro", cliente=ollama(cuerpo={"embeddings": [[0.1] * 768]}))
