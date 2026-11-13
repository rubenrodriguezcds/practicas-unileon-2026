"""Tests de /api/proyectos y /api/documentos (issue #7) sin base de datos real.

Para qué: fijar el contrato que usan las pantallas de proyectos (códigos, mensajes y forma de los
datos) y las reglas de la issue y de su diseño: solo el administrador entra (401/403 en TODOS los
endpoints), nombre de proyecto único sin distinguir mayúsculas (409) y borrar un proyecto borra sus
documentos.

Cómo: la misma app y bbdd en memoria (tests/factories.py) que test_roles.py; FakeDB aplica las
mismas reglas que la bbdd real (únicos sin mayúsculas y borrado en cascada).
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha

# Todos los endpoints, para comprobar que ninguno se queda sin proteger.
ENDPOINTS = [
    ("get", "/api/proyectos", None),
    ("post", "/api/proyectos", {"nombre": "x"}),
    ("get", "/api/proyectos/1", None),
    ("put", "/api/proyectos/1", {"nombre": "x"}),
    ("delete", "/api/proyectos/1", None),
    ("post", "/api/proyectos/1/documentos", None),
    ("get", "/api/documentos/1", None),
    ("delete", "/api/documentos/1", None),
]


@pytest.fixture
def fake():
    """admin/secreto (admin) y pepe/clave (usuario normal)."""
    f = FakeDB()
    f.users["pepe"] = f.user("clave", "pepe@example.com")
    return f


def make_client(fake, monkeypatch, **settings):
    app = create_app(make_settings(**settings))
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    return TestClient(app)


@pytest.fixture
def anon(fake, monkeypatch):
    """Cliente sin sesión."""
    return make_client(fake, monkeypatch)


def login(c, u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p, "altcha": solve_captcha(c.app.state.settings)})
    assert r.status_code == 200
    return c


@pytest.fixture
def admin(anon):
    return login(anon, "admin", "secreto")


def call(c, method, url, body):
    return c.request(method, url, json=body)


# --- permisos ---

@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_sin_sesion_es_401(anon, method, url, body):
    assert call(anon, method, url, body).status_code == 401


@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_usuario_normal_es_403(anon, fake, method, url, body):
    fake.add_project("x", {"a.pdf": b"%PDF"})
    login(anon, "pepe", "clave")
    assert call(anon, method, url, body).status_code == 403
    assert [p["nombre"] for p in fake.proyectos.values()] == ["x"] and len(fake.documentos) == 1


# --- listado ---

def test_listado_vacio(admin):
    r = admin.get("/api/proyectos")
    assert r.status_code == 200 and r.json() == []


def test_listado_por_nombre_sin_mayusculas_y_con_numero_de_documentos(admin, fake):
    fake.add_project("Beta", {"a.pdf": b"1", "b.txt": b"2"})
    fake.add_project("alfa")
    assert admin.get("/api/proyectos").json() == [
        {"id": 2, "nombre": "alfa", "tipo": None, "descripcion": None, "num_documentos": 0},
        {"id": 1, "nombre": "Beta", "tipo": None, "descripcion": None, "num_documentos": 2},
    ]


# --- crear ---

def test_crear(admin):
    r = admin.post("/api/proyectos", json={"nombre": "Web", "tipo": "Interno", "descripcion": "La web"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "nombre": "Web", "tipo": "Interno", "descripcion": "La web", "num_documentos": 0}
    assert len(admin.get("/api/proyectos").json()) == 1


def test_crear_limpia_espacios_y_vacios_son_null(admin):
    r = admin.post("/api/proyectos", json={"nombre": "  Web  ", "tipo": "  ", "descripcion": ""})
    assert r.json()["nombre"] == "Web" and r.json()["tipo"] is None and r.json()["descripcion"] is None


@pytest.mark.parametrize("body", [{}, {"nombre": ""}, {"nombre": "   "}, {"nombre": "x" * 101},
                                  {"nombre": "x", "tipo": "x" * 101}, {"nombre": "x", "descripcion": "x" * 1001}])
def test_crear_datos_no_validos_es_422(admin, body):
    assert admin.post("/api/proyectos", json=body).status_code == 422


def test_crear_nombre_repetido_con_otras_mayusculas_es_409(admin, fake):
    fake.add_project("Web")
    r = admin.post("/api/proyectos", json={"nombre": "web"})
    assert r.status_code == 409 and r.json()["detail"] == "Ya existe un proyecto con ese nombre"


# --- detalle ---

def test_detalle_con_documentos_por_nombre_y_visibles(admin, fake):
    pid = fake.add_project("Web", {"b.docx": b"12345", "a.pdf": b"%PDF"})
    r = admin.get(f"/api/proyectos/{pid}")
    assert r.status_code == 200
    assert r.json() == {
        "id": pid, "nombre": "Web", "tipo": None, "descripcion": None,
        "documentos": [
            {"id": 2, "nombre": "a.pdf", "tamano": 4, "visible": True},
            {"id": 1, "nombre": "b.docx", "tamano": 5, "visible": False},
        ],
    }


def test_detalle_inexistente_es_404(admin):
    r = admin.get("/api/proyectos/99")
    assert r.status_code == 404 and r.json()["detail"] == "El proyecto no existe"


# --- editar ---

def test_editar_nombre_tipo_y_descripcion(admin, fake):
    pid = fake.add_project("Web", {"a.pdf": b"1"}, tipo="Interno")
    r = admin.put(f"/api/proyectos/{pid}", json={"nombre": " Portal ", "tipo": "Cliente", "descripcion": "Nueva"})
    assert r.status_code == 200
    assert r.json() == {"id": pid, "nombre": "Portal", "tipo": "Cliente", "descripcion": "Nueva", "num_documentos": 1}
    assert fake.proyectos[pid] == {"nombre": "Portal", "tipo": "Cliente", "descripcion": "Nueva"}


def test_editar_vacios_son_null(admin, fake):
    pid = fake.add_project("Web", tipo="Interno", descripcion="Algo")
    r = admin.put(f"/api/proyectos/{pid}", json={"nombre": "Web", "tipo": "", "descripcion": "  "})
    assert r.json()["tipo"] is None and r.json()["descripcion"] is None


def test_editar_cambiando_solo_mayusculas_de_su_propio_nombre_vale(admin, fake):
    pid = fake.add_project("web")
    assert admin.put(f"/api/proyectos/{pid}", json={"nombre": "Web"}).json()["nombre"] == "Web"


def test_editar_con_nombre_de_otro_proyecto_es_409(admin, fake):
    fake.add_project("Web")
    pid = fake.add_project("App")
    r = admin.put(f"/api/proyectos/{pid}", json={"nombre": "WEB"})
    assert r.status_code == 409 and r.json()["detail"] == "Ya existe un proyecto con ese nombre"
    assert fake.proyectos[pid]["nombre"] == "App"


def test_editar_inexistente_es_404(admin):
    r = admin.put("/api/proyectos/99", json={"nombre": "x"})
    assert r.status_code == 404 and r.json()["detail"] == "El proyecto no existe"


@pytest.mark.parametrize("body", [{}, {"nombre": "  "}, {"nombre": "x" * 101}, {"nombre": "x", "descripcion": "x" * 1001}])
def test_editar_datos_no_validos_es_422(admin, fake, body):
    pid = fake.add_project("Web")
    assert admin.put(f"/api/proyectos/{pid}", json=body).status_code == 422


# --- borrar ---

def test_borrar_proyecto_borra_sus_documentos(admin, fake):
    pid = fake.add_project("Web", {"a.pdf": b"1", "b.pdf": b"2"})
    otro = fake.add_project("Otro", {"c.pdf": b"3"})
    assert admin.delete(f"/api/proyectos/{pid}").status_code == 204
    assert list(fake.proyectos) == [otro]
    assert [d["nombre"] for d in fake.documentos.values()] == ["c.pdf"]


def test_borrar_inexistente_es_404(admin):
    r = admin.delete("/api/proyectos/99")
    assert r.status_code == 404 and r.json()["detail"] == "El proyecto no existe"



# --- subir documentos ---

def subir(c, pid, nombre, contenido=b"%PDF-1.4 contenido"):
    return c.post(f"/api/proyectos/{pid}/documentos", files={"archivo": (nombre, contenido)})


def test_subir(admin, fake):
    pid = fake.add_project("Web")
    r = subir(admin, pid, "a.pdf", b"12345")
    assert r.status_code == 201
    assert r.json() == {"id": 1, "nombre": "a.pdf", "tamano": 5}
    assert fake.documentos[1] == {"proyecto_id": pid, "nombre": "a.pdf", "contenido": b"12345"}


def test_subir_nombre_con_ruta_guarda_solo_el_nombre(admin, fake):
    pid = fake.add_project("Web")
    assert subir(admin, pid, "C:\\Users\\ana\\a.pdf").json()["nombre"] == "a.pdf"


@pytest.mark.parametrize("nombre", ["x.html", "x.svg", "x.exe", "sin_extension"])
def test_subir_tipo_no_permitido_es_415(admin, fake, nombre):
    pid = fake.add_project("Web")
    r = subir(admin, pid, nombre)
    assert r.status_code == 415 and r.json()["detail"] == "Tipo de archivo no permitido"
    assert fake.documentos == {}


def test_subir_vacio_es_422(admin, fake):
    pid = fake.add_project("Web")
    r = subir(admin, pid, "a.pdf", b"")
    assert r.status_code == 422 and r.json()["detail"] == "El archivo está vacío"


def test_subir_nombre_repetido_con_otras_mayusculas_es_409(admin, fake):
    pid = fake.add_project("Web", {"a.pdf": b"1"})
    r = subir(admin, pid, "A.PDF")
    assert r.status_code == 409 and r.json()["detail"] == "Ya existe un documento con ese nombre en el proyecto"


def test_subir_mismo_nombre_con_otra_extension_vale(admin, fake):
    pid = fake.add_project("Web", {"a.pdf": b"1"})
    assert subir(admin, pid, "a.docx").status_code == 201


def test_subir_mismo_nombre_en_otro_proyecto_vale(admin, fake):
    fake.add_project("Web", {"a.pdf": b"1"})
    otro = fake.add_project("Otro")
    assert subir(admin, otro, "a.pdf").status_code == 201


def test_subir_a_proyecto_inexistente_es_404(admin):
    r = subir(admin, 99, "a.pdf")
    assert r.status_code == 404 and r.json()["detail"] == "El proyecto no existe"


def test_subir_mas_del_maximo_es_413(fake, monkeypatch):
    c = login(make_client(fake, monkeypatch, documento_max_mb=1), "admin", "secreto")
    pid = fake.add_project("Web")
    r = subir(c, pid, "a.pdf", b"x" * (1024 * 1024 + 1))
    assert r.status_code == 413 and r.json()["detail"] == "El archivo pasa de 1 MB"
    assert subir(c, pid, "b.pdf", b"x" * (1024 * 1024)).status_code == 201  # justo el máximo vale


# Ids que FastAPI acepta como 1 aunque no sean «solo dígitos»: el límite no puede depender de la forma de la ruta.
@pytest.mark.parametrize("pid", ["1", "+1", "%201", "1_0", "01"])
def test_content_length_excesivo_se_corta_sin_leer_el_cuerpo(anon, fake, pid):
    fake.add_project("Web")
    r = anon.post(f"/api/proyectos/{pid}/documentos", content=b"poco",
                  headers={"Content-Length": str(10 * 1024**3), "Content-Type": "multipart/form-data; boundary=x"})
    assert r.status_code == 413 and r.json()["detail"] == "El archivo pasa de 50 MB"
    assert fake.documentos == {}


def test_peticion_json_excesiva_no_habla_de_archivos(anon):
    r = anon.post("/api/auth/login", content=b"{}",
                  headers={"Content-Length": str(10 * 1024**3), "Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["detail"] == "La petición es demasiado grande"


def test_subir_nombre_con_acentos_de_mac_choca_con_el_de_windows(admin, fake):
    """macOS manda «é» como «e» + tilde suelta (NFD); se guarda normalizado (NFC) para que el 409 funcione."""
    pid = fake.add_project("Web", {"Memoria t\u00e9cnica.pdf": b"1"})
    r = subir(admin, pid, "Memoria te\u0301cnica.pdf")
    assert r.status_code == 409


def test_sin_content_length_y_por_trozos_es_411(admin, fake):
    pid = fake.add_project("Web")
    r = admin.post(f"/api/proyectos/{pid}/documentos", content=iter([b"trozo"]),
                   headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert r.status_code == 411


def test_anonimo_no_hace_que_se_procese_la_subida(anon, fake, monkeypatch):
    """Sin sesión se responde 401 SIN leer el multipart: nadie de fuera puede hacer trabajar al servidor."""
    from starlette.formparsers import MultiPartParser

    def no_deberia_llamarse(self):
        raise AssertionError("se ha procesado el multipart antes de comprobar la sesión")

    monkeypatch.setattr(MultiPartParser, "parse", no_deberia_llamarse)
    pid = fake.add_project("Web")
    assert subir(anon, pid, "a.pdf").status_code == 401


def test_subir_sin_campo_archivo_es_422(admin, fake):
    pid = fake.add_project("Web")
    r = admin.post(f"/api/proyectos/{pid}/documentos", files={"otro": ("a.pdf", b"1")})
    assert r.status_code == 422


# --- descargar y ver ---

SEGURIDAD = {"x-content-type-options": "nosniff", "cache-control": "private, no-store"}


def test_descargar_por_defecto_como_adjunto(admin, fake):
    pid = fake.add_project("Web", {"a.pdf": b"%PDF-contenido"})
    r = admin.get("/api/documentos/1")
    assert r.status_code == 200 and r.content == b"%PDF-contenido"
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert all(r.headers[k] == v for k, v in SEGURIDAD.items())
    assert pid


def test_pdf_sin_sandbox_para_que_el_visor_lo_muestre(admin, fake):
    """El visor de PDF de Chrome se queda en blanco con CSP sandbox; un PDF no ejecuta JS de página."""
    fake.add_project("Web", {"a.pdf": b"%PDF"})
    assert "content-security-policy" not in admin.get("/api/documentos/1?ver=1").headers


@pytest.mark.parametrize("nombre", ["a.png", "a.txt", "a.docx"])
def test_resto_de_tipos_con_sandbox(admin, fake, nombre):
    fake.add_project("Web", {nombre: b"x"})
    assert admin.get("/api/documentos/1?ver=1").headers["content-security-policy"] == "sandbox"


def test_ver_pdf_se_abre_en_el_navegador(admin, fake):
    fake.add_project("Web", {"a.pdf": b"%PDF"})
    r = admin.get("/api/documentos/1?ver=1")
    assert r.headers["content-disposition"].startswith("inline;")
    assert all(r.headers[k] == v for k, v in SEGURIDAD.items())


def test_ver_docx_se_descarga_igual(admin, fake):
    fake.add_project("Web", {"a.docx": b"PK"})
    r = admin.get("/api/documentos/1?ver=1")
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_descargar_nombre_con_acentos(admin, fake):
    fake.add_project("Web", {"Memoria técnica.pdf": b"%PDF"})
    assert "filename*=UTF-8''Memoria%20t%C3%A9cnica.pdf" in admin.get("/api/documentos/1").headers["content-disposition"]


def test_texto_en_utf8_se_sirve_como_utf8(admin, fake):
    fake.add_project("Web", {"a.csv": "año;horas\n".encode()})
    assert admin.get("/api/documentos/1?ver=1").headers["content-type"] == "text/plain; charset=utf-8"


def test_texto_que_no_es_utf8_se_sirve_como_windows_1252(admin, fake):
    """El Excel en español guarda los CSV en Windows-1252: con charset=utf-8 las tildes saldrían rotas."""
    fake.add_project("Web", {"a.csv": "año;horas\n".encode("cp1252")})
    r = admin.get("/api/documentos/1?ver=1")
    assert r.headers["content-type"] == "text/plain; charset=windows-1252"
    assert r.text == "año;horas\n"


def test_enlace_del_navegador_sin_sesion_lleva_al_login(anon, fake):
    """«Ver» y «Descargar» son enlaces: con la sesión caducada, al login y no un JSON de error."""
    fake.add_project("Web", {"a.pdf": b"%PDF"})
    r = anon.get("/api/documentos/1", headers={"Accept": "text/html,*/*"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_enlace_del_navegador_de_usuario_normal_sigue_siendo_403(anon, fake):
    fake.add_project("Web", {"a.pdf": b"%PDF"})
    login(anon, "pepe", "clave")
    r = anon.get("/api/documentos/1", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 403


def test_borrar_documento_sin_sesion_sigue_siendo_401(anon, fake):
    fake.add_project("Web", {"a.pdf": b"%PDF"})
    r = anon.delete("/api/documentos/1", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 401 and len(fake.documentos) == 1


def test_descargar_inexistente_es_404(admin):
    r = admin.get("/api/documentos/99")
    assert r.status_code == 404 and r.json()["detail"] == "El documento no existe"


# --- borrar documentos ---

def test_borrar_documento(admin, fake):
    pid = fake.add_project("Web", {"a.pdf": b"1", "b.pdf": b"2"})
    assert admin.delete("/api/documentos/1").status_code == 204
    assert [d["nombre"] for d in admin.get(f"/api/proyectos/{pid}").json()["documentos"]] == ["b.pdf"]


def test_borrar_documento_inexistente_es_404(admin):
    r = admin.delete("/api/documentos/99")
    assert r.status_code == 404 and r.json()["detail"] == "El documento no existe"
