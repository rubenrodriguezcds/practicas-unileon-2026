"""Tests de docling_cliente.py con un Docling simulado (httpx.MockTransport).

Las respuestas imitan las reales de docling-serve 1.38.2 con las muestras de prueba_docling/.
"""

import httpx
import pytest
from docling_cliente import DoclingError, Trozo, trocear

URL = "http://docling:5001"

OK = {
    "chunks": [
        {"chunk_index": 0, "text": "La migración costará 48.500 €.", "headings": ["Proyecto Alfa", "Resumen"],
         "page_numbers": [1], "num_tokens": 12},
        {"chunk_index": 1, "text": "Sin título ni página", "headings": None, "page_numbers": [], "num_tokens": 4},
        {"chunk_index": 2, "text": "   ", "headings": None, "page_numbers": [], "num_tokens": 0},
    ],
    "documents": [{"status": "success", "errors": [], "content": {"json_content": {"name": "memoria"}}}],
}
FALLO = {"chunks": [], "documents": [{"status": "failure", "content": {"json_content": None}, "errors": [
    {"error_message": "An unexpected error occurred while opening the document memoria.doc."}]}]}


def cliente(respuesta=OK, codigo=200, peticiones=None):
    def manejar(req: httpx.Request):
        if peticiones is not None:
            peticiones.append(req)
        if req.url.path == "/version":
            return httpx.Response(200, json={"docling-serve": "1.38.2"})
        return httpx.Response(codigo, json=respuesta)
    return httpx.Client(transport=httpx.MockTransport(manejar))


def test_mapea_trozos_json_y_version():
    peticiones = []
    r = trocear(URL, "memoria.docx", b"x", cliente(peticiones=peticiones))
    assert r.trozos == [Trozo("La migración costará 48.500 €.", ["Proyecto Alfa", "Resumen"], [1]),
                        Trozo("Sin título ni página", [], [])]  # el trozo vacío se descarta
    assert r.docling_json == {"name": "memoria"} and r.version == "1.38.2"
    post = peticiones[-1]
    assert post.url.path == "/v1/chunk/hybrid/file"
    cuerpo = post.content.decode("utf-8", "replace")
    assert 'name="include_converted_doc"' in cuerpo and 'name="convert_ocr_lang"' in cuerpo


def test_documento_que_docling_no_lee_es_error_con_su_mensaje():
    with pytest.raises(DoclingError, match="opening the document memoria.doc"):
        trocear(URL, "memoria.doc", b"x", cliente(FALLO))


def test_error_http_es_error():
    with pytest.raises(DoclingError, match="respondió 500"):
        trocear(URL, "a.pdf", b"x", cliente({"detail": "boom"}, codigo=500))


def test_docling_caido_es_error():
    def caido(req):
        raise httpx.ConnectError("connection refused")
    with pytest.raises(DoclingError, match="no responde"):
        trocear(URL, "a.pdf", b"x", httpx.Client(transport=httpx.MockTransport(caido)))
