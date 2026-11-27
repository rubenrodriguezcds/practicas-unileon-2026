"""Tests de GET /api/busqueda (buscador de prueba del asistente) sin bbdd ni Ollama reales.

Para qué: fijar el contrato que usará la página «Buscador»: solo el administrador (401/403), la
pregunta es obligatoria y corta (422), los fallos de Ollama dan 503/502 con un mensaje claro, y los
resultados salen tal cual los ordena la bbdd, con el filtro de proyecto pasado a la consulta.

Cómo: la app y la bbdd en memoria de tests/factories.py; `vectorizar_pregunta` se sustituye por un
doble que apunta con qué se le llamó. El SQL de la búsqueda híbrida se prueba con la bbdd real.
"""

import pytest
from fastapi.testclient import TestClient

from app import db, embeddings, resumen
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha

VECTOR = [0.5] * 1024
RESULTADO = {"documento_id": 8, "documento": "informe.pdf", "proyecto_id": 1, "proyecto": "Prueba IA",
             "titulos": ["1. Resumen"], "paginas": [1], "texto": "1. Resumen\nLa migración costará 48.500 €.",
             "puntuacion_vector": 0.71, "puntuacion_texto": 0.06, "puntuacion": 0.0328}


@pytest.fixture
def fake():
    f = FakeDB()
    f.users["pepe"] = f.user("clave")
    f.resultados_busqueda = [RESULTADO, {**RESULTADO, "documento_id": 5, "documento": "memoria.docx"}]
    return f


@pytest.fixture
def llamadas(monkeypatch):
    """Sustituye a Ollama: devuelve VECTOR y apunta (texto, url, modelo)."""
    hechas = []

    def vectorizar(texto, url, modelo):
        hechas.append((texto, url, modelo))
        return VECTOR

    monkeypatch.setattr(embeddings, "vectorizar_pregunta", vectorizar)
    return hechas


def cliente(fake, monkeypatch, usuario=None, clave=None):
    app = create_app(make_settings(ollama_url="http://ollama:11434", embeddings_modelo="bge-m3"))
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    c = TestClient(app)
    if usuario:
        r = c.post("/api/auth/login", json={"username": usuario, "password": clave,
                                            "altcha": solve_captcha(app.state.settings)})
        assert r.status_code == 200
    return c


@pytest.fixture
def admin(fake, monkeypatch, llamadas):
    return cliente(fake, monkeypatch, "admin", "secreto")


def test_sin_sesion_401(fake, monkeypatch, llamadas):
    assert cliente(fake, monkeypatch).get("/api/busqueda", params={"q": "migración"}).status_code == 401


def test_usuario_normal_403(fake, monkeypatch, llamadas):
    c = cliente(fake, monkeypatch, "pepe", "clave")
    assert c.get("/api/busqueda", params={"q": "migración"}).status_code == 403
    assert llamadas == []  # no se gasta Ollama en quien no puede buscar


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}, {"q": "x" * 501}, {"q": "a", "proyecto_id": "dos"}])
def test_pregunta_vacia_larga_o_proyecto_no_numerico_422(admin, llamadas, params):
    assert admin.get("/api/busqueda", params=params).status_code == 422
    assert llamadas == []


def test_devuelve_los_resultados_en_el_orden_de_la_bbdd(admin, fake, llamadas):
    r = admin.get("/api/busqueda", params={"q": "  ¿cuánto cuesta la migración?  "})
    assert r.status_code == 200
    assert [x["documento"] for x in r.json()] == ["informe.pdf", "memoria.docx"]
    assert r.json()[0] == RESULTADO
    assert llamadas == [("¿cuánto cuesta la migración?", "http://ollama:11434", "bge-m3")]
    assert fake.busquedas == [(VECTOR, "¿cuánto cuesta la migración?", None)]


def test_el_filtro_de_proyecto_llega_a_la_bbdd(admin, fake, llamadas):
    assert admin.get("/api/busqueda", params={"q": "riesgos", "proyecto_id": 3}).status_code == 200
    assert fake.busquedas == [(VECTOR, "riesgos", 3)]


def test_sin_resultados_lista_vacia(admin, fake, llamadas):
    fake.resultados_busqueda = []
    assert admin.get("/api/busqueda", params={"q": "tortilla"}).json() == []


def test_ollama_caido_503_con_mensaje_claro(admin, fake, monkeypatch):
    def caido(texto, url, modelo):
        raise embeddings.OllamaNoDisponible("Ollama no responde en http://ollama:11434 (ConnectError)")

    monkeypatch.setattr(embeddings, "vectorizar_pregunta", caido)
    r = admin.get("/api/busqueda", params={"q": "migración"})
    assert r.status_code == 503
    assert r.json()["detail"] == ("El buscador no está disponible: Ollama no responde en "
                                  "http://ollama:11434 (ConnectError)")
    assert fake.busquedas == []


def test_error_de_ollama_502_con_su_mensaje(admin, monkeypatch):
    def sin_modelo(texto, url, modelo):
        raise embeddings.EmbeddingsError("Ollama respondió 404: model 'bge-m3' not found")

    monkeypatch.setattr(embeddings, "vectorizar_pregunta", sin_modelo)
    r = admin.get("/api/busqueda", params={"q": "migración"})
    assert r.status_code == 502
    assert r.json()["detail"] == "Ollama respondió 404: model 'bge-m3' not found"


# --- resumen con IA: GET /api/busqueda/resumen ---

@pytest.fixture
def resumenes(monkeypatch):
    """Sustituye al modelo: apunta (pregunta, trozos, url, modelo) y devuelve un texto fijo."""
    hechas = []

    def resumir(pregunta, trozos, url, modelo):
        hechas.append((pregunta, trozos, url, modelo))
        return "La migración costará 48.500 € [1]."

    monkeypatch.setattr(resumen, "resumir", resumir)
    return hechas


def test_resumen_sin_sesion_401_y_usuario_normal_403(fake, monkeypatch, llamadas, resumenes):
    assert cliente(fake, monkeypatch).get("/api/busqueda/resumen", params={"q": "x"}).status_code == 401
    c = cliente(fake, monkeypatch, "pepe", "clave")
    assert c.get("/api/busqueda/resumen", params={"q": "x"}).status_code == 403
    assert resumenes == []


@pytest.mark.parametrize("params", [{}, {"q": "  "}, {"q": "x" * 501}])
def test_resumen_pregunta_vacia_o_larga_422(admin, resumenes, params):
    assert admin.get("/api/busqueda/resumen", params=params).status_code == 422
    assert resumenes == []


def test_resumen_con_los_primeros_trozos_de_la_misma_busqueda(admin, fake, resumenes):
    fake.resultados_busqueda = [{**RESULTADO, "documento_id": n} for n in range(10)]
    r = admin.get("/api/busqueda/resumen", params={"q": " ¿cuánto cuesta? ", "proyecto_id": 3})
    assert r.status_code == 200
    assert r.json() == {"resumen": "La migración costará 48.500 € [1].", "fuentes": 4, "encontrado": True}
    pregunta, trozos, url, modelo = resumenes[0]
    # Los mismos 4 primeros que pinta la página: así [1]…[4] señalan a los resultados de arriba.
    assert pregunta == "¿cuánto cuesta?" and [t["documento_id"] for t in trozos] == [0, 1, 2, 3]
    assert (url, modelo) == ("http://ollama:11434", "gemma4:e2b")
    assert fake.busquedas == [(VECTOR, "¿cuánto cuesta?", 3)]


def test_resumen_sin_resultados_no_llama_al_modelo(admin, fake, resumenes):
    fake.resultados_busqueda = []
    assert admin.get("/api/busqueda/resumen", params={"q": "tortilla"}).json() == {
        "resumen": None, "fuentes": 0, "encontrado": False}
    assert resumenes == []


def test_resumen_que_no_encuentra_la_respuesta_lo_marca(admin, fake, monkeypatch):
    fake.resultados_busqueda = [RESULTADO]
    monkeypatch.setattr(resumen, "resumir", lambda *a: "No lo encuentro en los documentos.")
    assert admin.get("/api/busqueda/resumen", params={"q": "¿quién ganó el mundial?"}).json() == {
        "resumen": "No lo encuentro en los documentos.", "fuentes": 1, "encontrado": False}


def test_resumen_modelo_caido_503(admin, monkeypatch):
    def caido(pregunta, trozos, url, modelo):
        raise resumen.ResumenNoDisponible("Ollama no responde en http://ollama:11434 (ReadTimeout)")

    monkeypatch.setattr(resumen, "resumir", caido)
    r = admin.get("/api/busqueda/resumen", params={"q": "migración"})
    assert r.status_code == 503
    assert r.json()["detail"] == "El resumen no está disponible: Ollama no responde en http://ollama:11434 (ReadTimeout)"


def test_resumen_error_del_modelo_502(admin, monkeypatch):
    def sin_modelo(pregunta, trozos, url, modelo):
        raise resumen.ResumenError("Ollama respondió 404: model 'gemma4:e2b' not found")

    monkeypatch.setattr(resumen, "resumir", sin_modelo)
    r = admin.get("/api/busqueda/resumen", params={"q": "migración"})
    assert r.status_code == 502 and "not found" in r.json()["detail"]
