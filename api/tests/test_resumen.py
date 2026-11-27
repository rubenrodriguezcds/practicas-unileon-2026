"""Tests de app/resumen.py (resumen con IA del buscador) con un Ollama simulado (httpx.MockTransport).

Para qué: fijar lo que se le manda al modelo (la pregunta y los fragmentos numerados, para que
cite [1], [2]…; sin streaming; contexto de 8192) y que los fallos de Ollama dan errores claros.
"""

import json

import httpx
import pytest

from app.resumen import ResumenError, ResumenNoDisponible, encontrado, resumir

URL = "http://ollama:11434"
TROZOS = [
    {"documento": "informe.pdf", "paginas": [1], "texto": "La migración costará 48.500 €."},
    {"documento": "memoria.docx", "paginas": [], "texto": "Se hará en tres fases."},
]


def ollama(codigo=200, cuerpo=None, peticiones=None):
    def responder(request):
        if peticiones is not None:
            peticiones.append((request.url.path, json.loads(request.read())))
        return httpx.Response(codigo, json=cuerpo if cuerpo is not None else
                              {"message": {"role": "assistant", "content": "  Cuesta 48.500 € [1].\n"}})

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_manda_la_pregunta_y_los_fragmentos_numerados_y_devuelve_el_texto():
    peticiones = []
    texto = resumir("¿cuánto cuesta?", TROZOS, URL, "gemma4:e2b", cliente=ollama(peticiones=peticiones))
    assert texto == "Cuesta 48.500 € [1]."
    ruta, cuerpo = peticiones[0]
    assert ruta == "/api/chat"
    assert cuerpo["model"] == "gemma4:e2b" and cuerpo["stream"] is False
    assert cuerpo["options"]["num_ctx"] == 8192
    usuario = cuerpo["messages"][-1]["content"]
    assert "[1] Documento: informe.pdf, página 1\nLa migración costará 48.500 €." in usuario
    assert "[2] Documento: memoria.docx, página -" in usuario  # Word no tiene páginas
    assert usuario.endswith("Pregunta: ¿cuánto cuesta?")
    assert "No lo encuentro en los documentos" in cuerpo["messages"][0]["content"]


def test_ollama_caido():
    def caido(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ResumenNoDisponible, match="Ollama no responde en http://ollama:11434"):
        resumir("x", TROZOS, URL, "gemma4:e2b", cliente=httpx.Client(transport=httpx.MockTransport(caido)))


def test_error_de_ollama_con_su_mensaje():
    with pytest.raises(ResumenError, match="404: model 'gemma4:e2b' not found"):
        resumir("x", TROZOS, URL, "gemma4:e2b",
                cliente=ollama(404, {"error": "model 'gemma4:e2b' not found"}))


@pytest.mark.parametrize("texto, esperado", [
    ("Cuesta 48.500 € [1].", True),
    ("No lo encuentro en los documentos.", False),
    ("«No lo encuentro en los documentos.»", False),  # a veces copia también las comillas
    ("no lo encuentro en los documentos", False),
])
def test_encontrado(texto, esperado):
    assert encontrado(texto) is esperado
