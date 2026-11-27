"""Tests de las validaciones de contenido por proyecto (CRUD) sin base de datos real.

Para qué: fijar el contrato que usará la sección «Validación» de la ficha del proyecto: solo el
administrador (401/403 en TODOS los endpoints), 404 si el proyecto o la validación no existen, 422
con datos no válidos (también un patrón que no es una expresión regular), el orden en que se
crean, y que editar una validación borra su resultado (ya no corresponde a lo que se comprueba).

Cómo: la app y la bbdd en memoria de tests/factories.py, como test_proyectos.py. La ejecución de
las validaciones (patrón e IA) tiene sus propios tests.
"""

import pytest
from fastapi.testclient import TestClient

from app import db, llm
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha

ENDPOINTS = [
    ("get", "/api/proyectos/1/validaciones", None),
    ("post", "/api/proyectos/1/validaciones", {"nombre": "x", "tipo": "patron", "criterio": "x"}),
    ("put", "/api/validaciones/1", {"nombre": "x", "tipo": "patron", "criterio": "x"}),
    ("delete", "/api/validaciones/1", None),
]
VLAN = {"nombre": "Aparecen las VLAN", "tipo": "patron", "criterio": r"\mVLAN\s*\d+"}
RUTAS = {"nombre": "Tabla de rutas", "tipo": "ia", "criterio": "¿Está definida la tabla de rutas?"}


@pytest.fixture(autouse=True)
def gemma(monkeypatch):
    """Doble del modelo de lenguaje (resumen de los patrones que se cumplen): apunta sus llamadas."""
    llamadas = {"chat": [], "respuesta": {"resumen": "Las VLAN 10 y 20 aparecen en el diseño de red."}}

    def chat(url, modelo, mensajes, esquema):
        llamadas["chat"].append(mensajes)
        if isinstance(llamadas["respuesta"], Exception):
            raise llamadas["respuesta"]
        return llamadas["respuesta"]

    monkeypatch.setattr(llm, "chat_json", chat)
    return llamadas


@pytest.fixture
def fake():
    f = FakeDB()
    f.users["pepe"] = f.user("clave")
    f.add_project("Red Norte")  # id 1
    return f


def cliente(fake, monkeypatch, usuario=None, clave=None):
    app = create_app(make_settings())
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    c = TestClient(app)
    if usuario:
        r = c.post("/api/auth/login", json={"username": usuario, "password": clave,
                                            "altcha": solve_captcha(app.state.settings)})
        assert r.status_code == 200
    return c


@pytest.fixture
def admin(fake, monkeypatch):
    return cliente(fake, monkeypatch, "admin", "secreto")


@pytest.mark.parametrize("method, url, body", ENDPOINTS)
def test_sin_sesion_401(fake, monkeypatch, method, url, body):
    assert cliente(fake, monkeypatch).request(method, url, json=body).status_code == 401


@pytest.mark.parametrize("method, url, body", ENDPOINTS)
def test_usuario_normal_403(fake, monkeypatch, method, url, body):
    assert cliente(fake, monkeypatch, "pepe", "clave").request(method, url, json=body).status_code == 403


def test_crear_y_listar_en_el_orden_en_que_se_crean(admin):
    r = admin.post("/api/proyectos/1/validaciones", json=VLAN)
    assert r.status_code == 201
    assert r.json() == {"id": 1, "proyecto_id": 1, **VLAN, "orden": 1, "resultado": None}
    admin.post("/api/proyectos/1/validaciones", json=RUTAS)
    lista = admin.get("/api/proyectos/1/validaciones").json()
    assert [(v["nombre"], v["orden"]) for v in lista] == [("Aparecen las VLAN", 1), ("Tabla de rutas", 2)]


def test_el_nombre_y_el_criterio_se_guardan_sin_espacios_a_los_lados(admin):
    r = admin.post("/api/proyectos/1/validaciones", json={**RUTAS, "nombre": "  Rutas  ", "criterio": "  ¿Rutas?  "})
    assert (r.json()["nombre"], r.json()["criterio"]) == ("Rutas", "¿Rutas?")


def test_proyecto_sin_validaciones_lista_vacia(admin):
    assert admin.get("/api/proyectos/1/validaciones").json() == []


def test_proyecto_inexistente_404(admin):
    assert admin.get("/api/proyectos/99/validaciones").status_code == 404
    assert admin.post("/api/proyectos/99/validaciones", json=VLAN).status_code == 404


@pytest.mark.parametrize("body", [
    {**VLAN, "nombre": "   "}, {**VLAN, "criterio": ""}, {**VLAN, "tipo": "regex"},
    {"nombre": "x", "tipo": "patron"}, {**VLAN, "nombre": "x" * 201}, {**RUTAS, "criterio": "x" * 1001},
])
def test_datos_no_validos_422(admin, body):
    assert admin.post("/api/proyectos/1/validaciones", json=body).status_code == 422


def test_patron_que_no_es_expresion_regular_422_con_mensaje(admin, fake):
    r = admin.post("/api/proyectos/1/validaciones", json={**VLAN, "criterio": "VLAN (sin cerrar"})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("El patrón no es una expresión regular válida")
    assert fake.validaciones == {}


def test_una_pregunta_de_ia_no_se_comprueba_como_patron(admin):
    # «¿Está…?» no es una expresión regular válida, pero en una validación de IA es texto normal.
    assert admin.post("/api/proyectos/1/validaciones", json={**RUTAS, "criterio": "¿Está (la tabla?"}).status_code == 201


def test_editar_cambia_los_datos_y_borra_el_resultado(admin, fake):
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    fake.resultados[vid] = {"estado": "ok", "explicacion": "Aparece", "resumen": None, "fragmentos": [],
                            "ejecutada": "2026-11-27T10:00:00+00:00"}
    assert admin.get("/api/proyectos/1/validaciones").json()[0]["resultado"]["estado"] == "ok"
    r = admin.put(f"/api/validaciones/{vid}", json={**VLAN, "criterio": r"\mVLAN\M"})
    assert r.status_code == 200
    assert r.json()["criterio"] == r"\mVLAN\M" and r.json()["resultado"] is None
    assert vid not in fake.resultados


def test_editar_inexistente_404_y_patron_no_valido_422(admin):
    assert admin.put("/api/validaciones/99", json=VLAN).status_code == 404
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    assert admin.put(f"/api/validaciones/{vid}", json={**VLAN, "criterio": "[sin cerrar"}).status_code == 422


def test_borrar(admin):
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    assert admin.delete(f"/api/validaciones/{vid}").status_code == 204
    assert admin.get("/api/proyectos/1/validaciones").json() == []
    assert admin.delete(f"/api/validaciones/{vid}").status_code == 404


def test_el_resultado_trae_sus_pruebas_en_orden_y_su_resumen(admin, fake):
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    fake.pruebas[7] = {"documento_id": 3, "documento": "diseño_red.pdf", "paginas": [3], "texto": "VLAN 10: gestión"}
    fake.pruebas[9] = {"documento_id": 4, "documento": "anexo.docx", "paginas": [], "texto": "VLAN 30: invitados"}
    fake.resultados[vid] = {"estado": "ok", "explicacion": "Aparece en 2 trozos de 2 documentos", "resumen": "Las VLAN…",
                            "fragmentos": [7, 9], "ejecutada": "2026-11-27T10:00:00+00:00"}
    assert admin.get("/api/proyectos/1/validaciones").json()[0]["resultado"] == {
        "estado": "ok", "explicacion": "Aparece en 2 trozos de 2 documentos", "resumen": "Las VLAN…",
        "ejecutada": "2026-11-27T10:00:00+00:00",
        "pruebas": [{"documento_id": 3, "documento": "diseño_red.pdf", "paginas": [3], "texto": "VLAN 10: gestión"},
                    {"documento_id": 4, "documento": "anexo.docx", "paginas": [], "texto": "VLAN 30: invitados"}],
    }


def test_borrar_el_proyecto_borra_sus_validaciones(admin, fake):
    admin.post("/api/proyectos/1/validaciones", json=VLAN)
    assert admin.delete("/api/proyectos/1").status_code == 204
    assert fake.validaciones == {}


# --- Ejecutar (paso 2: validaciones por patrón) ---

def test_ejecutar_exige_administrador(fake, monkeypatch):
    assert cliente(fake, monkeypatch).post("/api/validaciones/1/ejecutar").status_code == 401
    assert cliente(fake, monkeypatch, "pepe", "clave").post("/api/validaciones/1/ejecutar").status_code == 403


def test_ejecutar_inexistente_404(admin):
    assert admin.post("/api/validaciones/99/ejecutar").status_code == 404


def red(fake):
    """Proyecto 1 con dos documentos indexados: uno con VLAN (dos trozos) y otro sin."""
    d1 = fake.add_document(None, 1, "diseño_red.pdf", b"x")["id"]
    d2 = fake.add_document(None, 1, "presupuesto.xlsx", b"x")["id"]
    fake.indexado[d1] = fake.indexado[d2] = {"estado": "hecho", "error": None}
    fake.add_fragment(1, d1, "Esquema de red\nSe usan dos redes: la vlan 10 de gestión", [2])
    fake.add_fragment(1, d1, "VLAN 20: usuarios", [3])
    fake.add_fragment(1, d2, "Licencias, Importe = 12000", [1])
    return d1, d2


def test_patron_que_aparece_cumple_con_su_prueba_y_sin_distinguir_mayusculas(admin, fake):
    red(fake)
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    r = admin.post(f"/api/validaciones/{vid}/ejecutar")
    assert r.status_code == 200
    res = r.json()["resultado"]
    assert res["estado"] == "ok"
    assert res["explicacion"] == "Aparece en 2 trozos de 1 documento"
    # una prueba por documento: el primer trozo donde aparece
    assert res["pruebas"] == [{"documento_id": 1, "documento": "diseño_red.pdf", "paginas": [2],
                               "texto": "Esquema de red\nSe usan dos redes: la vlan 10 de gestión"}]
    assert res["resumen"] == "Las VLAN 10 y 20 aparecen en el diseño de red."
    # queda guardado: lo ve el listado
    assert admin.get("/api/proyectos/1/validaciones").json()[0]["resultado"]["estado"] == "ok"


def test_patron_que_no_aparece_no_cumple(admin, fake):
    red(fake)
    vid = admin.post("/api/proyectos/1/validaciones", json={**VLAN, "criterio": r"tabla de rutas"}).json()["id"]
    res = admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]
    assert (res["estado"], res["explicacion"], res["pruebas"]) == ("falla", "No aparece en ningún documento del proyecto", [])


def test_si_quedan_documentos_sin_indexar_lo_avisa(admin, fake):
    red(fake)
    fake.add_document(None, 1, "rutas.docx", b"x")  # sin fila en indexado: pendiente
    vid = admin.post("/api/proyectos/1/validaciones", json={**VLAN, "criterio": "rutas"}).json()["id"]
    res = admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]
    assert res["estado"] == "falla"
    assert res["explicacion"] == ("No aparece en ningún documento del proyecto "
                                  "(1 documento aún no está indexado: vuelve a validar cuando termine)")


def test_proyecto_sin_documentos_indexados(admin, fake):
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    res = admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]
    assert (res["estado"], res["explicacion"]) == ("falla", "El proyecto no tiene documentos indexados")


def test_solo_busca_en_los_trozos_de_su_proyecto(admin, fake):
    red(fake)
    otro = fake.add_project("Otro")
    d = fake.add_document(None, otro, "otro.pdf", b"x")["id"]
    fake.indexado[d] = {"estado": "hecho", "error": None}
    fake.add_fragment(otro, d, "tabla de rutas completa", [1])
    vid = admin.post("/api/proyectos/1/validaciones", json={**VLAN, "criterio": "tabla de rutas"}).json()["id"]
    assert admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]["estado"] == "falla"


def test_volver_a_ejecutar_sobrescribe_el_resultado(admin, fake):
    red(fake)
    vid = admin.post("/api/proyectos/1/validaciones", json={**VLAN, "criterio": "rutas"}).json()["id"]
    assert admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]["estado"] == "falla"
    d = fake.add_document(None, 1, "rutas.pdf", b"x")["id"]
    fake.indexado[d] = {"estado": "hecho", "error": None}
    fake.add_fragment(1, d, "Tabla de rutas estáticas", [1])
    assert admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]["estado"] == "ok"
    assert len(fake.resultados) == 1


def test_patron_que_falla_al_ejecutarse_queda_en_error(admin, fake):
    red(fake)
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    fake.validaciones[vid]["criterio"] = "[roto"  # p. ej. guardado antes de comprobarlo
    res = admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]
    assert res["estado"] == "error" and res["explicacion"].startswith("El patrón no es una expresión regular válida")


def test_el_patron_no_distingue_acentos(admin, fake):
    red(fake)
    fake.add_fragment(1, 1, "Plan de MIGRACIÓN de la red", [4])
    for patron in ("migracion", "migración", r"\mMIGRACION\M"):
        vid = admin.post("/api/proyectos/1/validaciones", json={**VLAN, "criterio": patron}).json()["id"]
        assert admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]["estado"] == "ok", patron


def test_el_desplegable_tiene_todos_los_documentos_donde_aparece(admin, fake):
    _, d2 = red(fake)
    d3 = fake.add_document(None, 1, "anexo.docx", b"x")["id"]
    fake.indexado[d3] = {"estado": "hecho", "error": None}
    fake.add_fragment(1, d3, "Anexo: VLAN 30 de invitados", [])
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    res = admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]
    assert res["explicacion"] == "Aparece en 3 trozos de 2 documentos"
    assert [p["documento"] for p in res["pruebas"]] == ["diseño_red.pdf", "anexo.docx"]


def test_el_resumen_de_un_patron_lo_escribe_la_ia_con_los_trozos_donde_aparece(admin, fake, gemma):
    red(fake)
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    admin.post(f"/api/validaciones/{vid}/ejecutar")
    pregunta = gemma["chat"][0][-1]["content"]
    assert "Aparecen las VLAN" in pregunta
    assert "diseño_red.pdf · pág. 2\nEsquema de red\nSe usan dos redes: la vlan 10 de gestión" in pregunta


def test_un_patron_que_no_se_cumple_no_llama_a_la_ia(admin, fake, gemma):
    red(fake)
    vid = admin.post("/api/proyectos/1/validaciones", json={**VLAN, "criterio": "tabla de rutas"}).json()["id"]
    assert admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]["resumen"] is None
    assert gemma["chat"] == []


@pytest.mark.parametrize("fallo", [llm.LLMNoDisponible("Ollama no responde"), llm.LLMError("formato")])
def test_si_la_ia_falla_el_patron_sigue_cumpliendo_sin_resumen(admin, fake, gemma, fallo):
    red(fake)
    gemma["respuesta"] = fallo
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    res = admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]
    assert (res["estado"], res["resumen"]) == ("ok", None)
    assert res["explicacion"] == "Aparece en 2 trozos de 1 documento"


@pytest.mark.parametrize("respuesta", [{"resumen": "   "}, {"resumen": 5}, {}])
def test_resumen_vacio_o_con_otra_forma_queda_sin_resumen(admin, fake, gemma, respuesta):
    red(fake)
    gemma["respuesta"] = respuesta
    vid = admin.post("/api/proyectos/1/validaciones", json=VLAN).json()["id"]
    assert admin.post(f"/api/validaciones/{vid}/ejecutar").json()["resultado"]["resumen"] is None
