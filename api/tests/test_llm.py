"""Tests de app/llm.py (llamar al modelo de lenguaje de Ollama pidiendo JSON) con un Ollama simulado.

Se fija la petición (modelo, mensajes, esquema del JSON, sin «pensar», temperatura 0) y los errores:
Ollama caído → LLMNoDisponible; error de Ollama o respuesta que no es el JSON pedido → LLMError.
"""

import json

import httpx
import pytest

from app.llm import LLMError, LLMNoDisponible, chat_json

URL = "http://ollama:11434"
MENSAJES = [{"role": "system", "content": "Eres un revisor."}, {"role": "user", "content": "¿Está?"}]
ESQUEMA = {"type": "object", "properties": {"cumple": {"type": "boolean"}}, "required": ["cumple"]}


def ollama(codigo=200, contenido='{"cumple": true}', peticiones=None):
    def responder(request):
        if peticiones is not None:
            peticiones.append(json.loads(request.content))
        if codigo != 200:
            return httpx.Response(codigo, json={"error": "model 'gemma4:e2b' not found"})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": contenido}})

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_devuelve_el_json_de_la_respuesta():
    assert chat_json(URL, "gemma4:e2b", MENSAJES, ESQUEMA, cliente=ollama()) == {"cumple": True}


def test_la_peticion_pide_json_con_esquema_sin_pensar_y_sin_azar():
    peticiones = []
    chat_json(URL, "gemma4:e2b", MENSAJES, ESQUEMA, cliente=ollama(peticiones=peticiones))
    p = peticiones[0]
    assert (p["model"], p["messages"], p["format"], p["stream"], p["think"]) == ("gemma4:e2b", MENSAJES, ESQUEMA, False, False)
    assert p["options"]["temperature"] == 0


def test_ollama_caido_es_no_disponible():
    def caido(request):
        raise httpx.ConnectError("Connection refused")

    with pytest.raises(LLMNoDisponible, match=f"Ollama no responde en {URL}"):
        chat_json(URL, "gemma4:e2b", MENSAJES, ESQUEMA, cliente=httpx.Client(transport=httpx.MockTransport(caido)))


def test_error_de_ollama_con_su_mensaje():
    with pytest.raises(LLMError, match="Ollama respondió 404: model 'gemma4:e2b' not found") as e:
        chat_json(URL, "gemma4:e2b", MENSAJES, ESQUEMA, cliente=ollama(404))
    assert not isinstance(e.value, LLMNoDisponible)


@pytest.mark.parametrize("contenido", ["Sí, está.", "[1, 2]", ""])
def test_respuesta_que_no_es_un_objeto_json_es_error(contenido):
    with pytest.raises(LLMError, match="no respondió en el formato esperado"):
        chat_json(URL, "gemma4:e2b", MENSAJES, ESQUEMA, cliente=ollama(contenido=contenido))
