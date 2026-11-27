"""Tests de las validaciones con IA (POST /api/validaciones/{id}/ejecutar con tipo «ia»).

Para qué: fijar las reglas para que la IA no «apruebe» sin pruebas:
  - se buscan los trozos parecidos del proyecto y, si ninguno pasa el umbral, ❌ sin preguntar a la IA;
  - la IA solo aprueba citando trozos de los que se le pasaron, y las pruebas guardadas son ESOS trozos
    (todos los que cite, en su orden, sin repetir), con un resumen corto para el desplegable;
  - «sí» sin ningún trozo válido → ❌; Ollama caído o respuesta rara → ⚠️ con el motivo.

Cómo: FakeDB (tests/factories.py) para la bbdd; `vectorizar_pregunta` y `chat_json` se sustituyen por
dobles que apuntan con qué se les llamó.
"""

import pytest
from fastapi.testclient import TestClient

from app import db, embeddings, llm
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha

RUTAS = {"nombre": "Tabla de rutas", "tipo": "ia", "criterio": "¿Está definida la tabla de rutas?"}
VECTOR = [0.5] * 1024


def trozo(fid, documento, texto, parecido, paginas=(1,)):
    return {"fragmento_id": fid, "documento_id": fid, "documento": documento, "proyecto_id": 1, "proyecto": "Red Norte",
            "titulos": [], "paginas": list(paginas), "texto": texto,
            "puntuacion_vector": parecido, "puntuacion_texto": None, "puntuacion": 0.016}


ENRUTAMIENTO = trozo(11, "diseño_red.pdf", "Rutas estáticas: 0.0.0.0/0 via 10.0.0.1", 0.62, (4,))
VLANES = trozo(12, "diseño_red.pdf", "VLAN 10 gestión, VLAN 20 usuarios", 0.48, (3,))


@pytest.fixture
def fake():
    f = FakeDB()
    f.add_project("Red Norte")  # id 1
    d = f.add_document(None, 1, "diseño_red.pdf", b"x")["id"]
    f.indexado[d] = {"estado": "hecho", "error": None}
    f.resultados_busqueda = [ENRUTAMIENTO, VLANES]
    for t in f.resultados_busqueda:
        f.pruebas[t["fragmento_id"]] = {"documento_id": d, "documento": t["documento"], "paginas": t["paginas"],
                                        "texto": t["texto"]}
    return f


@pytest.fixture
def ia(monkeypatch):
    """Dobles de Ollama: el vector de la pregunta y la respuesta de la IA (cambiable en cada test)."""
    llamadas = {"embed": [], "chat": [],
                "respuesta": {"cumple": True, "trozos": [1], "explicacion": "El trozo 1 define rutas estáticas.",
                              "resumen": "La ruta por defecto sale por 10.0.0.1 (diseño de red, pág. 4)."}}

    def vectorizar(texto, url, modelo):
        llamadas["embed"].append((texto, url, modelo))
        return VECTOR

    def chat(url, modelo, mensajes, esquema):
        llamadas["chat"].append((url, modelo, mensajes, esquema))
        if isinstance(llamadas["respuesta"], Exception):
            raise llamadas["respuesta"]
        return llamadas["respuesta"]

    monkeypatch.setattr(embeddings, "vectorizar_pregunta", vectorizar)
    monkeypatch.setattr(llm, "chat_json", chat)
    return llamadas


@pytest.fixture
def admin(fake, monkeypatch, ia):
    app = create_app(make_settings(ollama_url="http://ollama:11434", chat_modelo="gemma4:e2b", validacion_umbral=0.45))
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "secreto", "altcha": solve_captcha(app.state.settings)})
    assert r.status_code == 200
    return c


def ejecutar(admin, **cambios):
    vid = admin.post("/api/proyectos/1/validaciones", json={**RUTAS, **cambios}).json()["id"]
    r = admin.post(f"/api/validaciones/{vid}/ejecutar")
    assert r.status_code == 200
    return r.json()["resultado"]


def test_la_ia_aprueba_citando_un_trozo_y_la_prueba_es_ese_trozo(admin, fake, ia):
    res = ejecutar(admin)
    assert res["estado"] == "ok"
    assert res["explicacion"] == "El trozo 1 define rutas estáticas."
    assert res["resumen"] == "La ruta por defecto sale por 10.0.0.1 (diseño de red, pág. 4)."
    assert res["pruebas"] == [{"documento_id": 1, "documento": "diseño_red.pdf", "paginas": [4],
                               "texto": "Rutas estáticas: 0.0.0.0/0 via 10.0.0.1"}]
    # buscó en SU proyecto con la pregunta, y a la IA le llegaron la pregunta y los trozos numerados
    assert fake.busquedas == [(VECTOR, "¿Está definida la tabla de rutas?", 1)]
    url, modelo, mensajes, esquema = ia["chat"][0]
    assert (url, modelo) == ("http://ollama:11434", "gemma4:e2b")
    pregunta = mensajes[-1]["content"]
    assert "¿Está definida la tabla de rutas?" in pregunta
    assert "[1] diseño_red.pdf · pág. 4\nRutas estáticas: 0.0.0.0/0 via 10.0.0.1" in pregunta
    assert "[2] diseño_red.pdf · pág. 3\nVLAN 10 gestión, VLAN 20 usuarios" in pregunta
    assert set(esquema["required"]) == {"cumple", "trozos", "explicacion", "resumen"}


def test_cita_todos_los_trozos_que_lo_demuestran_en_su_orden_y_sin_repetir(admin, ia):
    ia["respuesta"] = {"cumple": True, "trozos": [2, 1, 2], "explicacion": "Sí.", "resumen": "En dos sitios."}
    assert [p["texto"] for p in ejecutar(admin)["pruebas"]] == ["VLAN 10 gestión, VLAN 20 usuarios",
                                                               "Rutas estáticas: 0.0.0.0/0 via 10.0.0.1"]


def test_los_numeros_que_no_son_de_ningun_trozo_se_ignoran(admin, ia):
    ia["respuesta"] = {"cumple": True, "trozos": [7, 1, 0], "explicacion": "Sí.", "resumen": "x"}
    assert [p["documento"] for p in ejecutar(admin)["pruebas"]] == ["diseño_red.pdf"]


def test_si_la_ia_dice_que_no_no_cumple_con_su_explicacion(admin, ia):
    ia["respuesta"] = {"cumple": False, "trozos": [], "explicacion": "Ningún trozo define la tabla de rutas.", "resumen": ""}
    res = ejecutar(admin)
    assert (res["estado"], res["explicacion"], res["pruebas"], res["resumen"]) == (
        "falla", "Ningún trozo define la tabla de rutas.", [], None)


@pytest.mark.parametrize("citados", [[], [0], [3, -1]])
def test_si_dice_que_si_sin_citar_un_trozo_valido_no_cumple(admin, ia, citados):
    ia["respuesta"] = {"cumple": True, "trozos": citados, "explicacion": "Sí.", "resumen": "x"}
    res = ejecutar(admin)
    assert res["estado"] == "falla" and res["pruebas"] == []
    assert res["explicacion"] == "La IA dijo que sí, pero no indicó en qué trozo lo encontró"


def test_sin_trozos_parecidos_no_pregunta_a_la_ia(admin, fake, ia):
    fake.resultados_busqueda = [trozo(13, "presupuesto.xlsx", "Licencias 12000", 0.31)]
    res = ejecutar(admin)
    assert res["estado"] == "falla"
    assert res["explicacion"] == "No aparece en ningún documento del proyecto (ningún trozo se parece lo suficiente)"
    assert ia["chat"] == []


def test_a_la_ia_solo_le_llegan_los_trozos_que_pasan_el_umbral(admin, fake, ia):
    fake.resultados_busqueda = [ENRUTAMIENTO, trozo(13, "presupuesto.xlsx", "Licencias 12000", 0.31)]
    ejecutar(admin)
    assert "presupuesto.xlsx" not in ia["chat"][0][2][-1]["content"]


def test_proyecto_sin_documentos_indexados(admin, fake, ia):
    fake.indexado.clear()
    fake.resultados_busqueda = []
    res = ejecutar(admin)
    assert (res["estado"], res["explicacion"]) == ("falla", "El proyecto no tiene documentos indexados "
                                                   "(1 documento aún no está indexado: vuelve a validar cuando termine)")
    assert ia["embed"] == [] and ia["chat"] == []


def test_avisa_de_los_documentos_pendientes_si_no_cumple(admin, fake, ia):
    fake.add_document(None, 1, "rutas.docx", b"x")
    ia["respuesta"] = {"cumple": False, "trozos": [], "explicacion": "No se define.", "resumen": ""}
    assert ejecutar(admin)["explicacion"] == "No se define. (1 documento aún no está indexado: vuelve a validar cuando termine)"


def test_ollama_caido_al_buscar_queda_en_error(admin, monkeypatch, ia):
    def caido(texto, url, modelo):
        raise embeddings.OllamaNoDisponible("Ollama no responde en http://ollama:11434 (ConnectError)")

    monkeypatch.setattr(embeddings, "vectorizar_pregunta", caido)
    res = ejecutar(admin)
    assert (res["estado"], res["explicacion"]) == ("error", "Ollama no responde en http://ollama:11434 (ConnectError)")


@pytest.mark.parametrize("fallo", [llm.LLMNoDisponible("Ollama no responde en http://ollama:11434 (ReadTimeout)"),
                                   llm.LLMError("La IA no respondió en el formato esperado")])
def test_fallo_de_la_ia_queda_en_error_con_el_motivo(admin, ia, fallo):
    ia["respuesta"] = fallo
    res = ejecutar(admin)
    assert (res["estado"], res["explicacion"]) == ("error", str(fallo))


@pytest.mark.parametrize("respuesta", [{"cumple": "sí", "trozos": [1], "explicacion": "x", "resumen": "x"},
                                       {"trozos": [1]}, {"cumple": True, "trozos": ["1"], "explicacion": "x", "resumen": "x"},
                                       {"cumple": True, "trozos": 1, "explicacion": "x", "resumen": "x"}])
def test_respuesta_de_la_ia_con_otra_forma_queda_en_error(admin, ia, respuesta):
    ia["respuesta"] = respuesta
    res = ejecutar(admin)
    assert (res["estado"], res["explicacion"]) == ("error", "La IA no respondió en el formato esperado")
