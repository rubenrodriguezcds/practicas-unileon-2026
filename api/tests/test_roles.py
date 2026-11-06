"""Tests de /api/roles (issue #5) sin base de datos real.

Para qué: fijar el contrato que usa la pantalla de roles (códigos, mensajes y forma de los datos)
y las reglas de la issue: solo el administrador entra (401/403 en TODOS los endpoints), el nombre
es único (409) y un rol que tienen usuarios no se borra (409).

Cómo: la misma app y bbdd en memoria (tests/factories.py) que test_auth.py; FakeDB aplica las
mismas reglas que la bbdd real.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha

# Todos los endpoints, para comprobar que ninguno se queda sin proteger.
ENDPOINTS = [
    ("get", "/api/roles", None),
    ("post", "/api/roles", {"nombre": "x"}),
    ("put", "/api/roles/1", {"nombre": "x"}),
    ("delete", "/api/roles/1", None),
    ("get", "/api/roles/1/usuarios", None),
]


@pytest.fixture
def fake():
    """admin/secreto (admin) y pepe/clave y ana/clave (usuarios normales)."""
    f = FakeDB()
    f.users["pepe"] = f.user("clave", "pepe@example.com")
    f.users["ana"] = f.user("clave")
    return f


@pytest.fixture
def anon(fake, monkeypatch):
    """Cliente sin sesión."""
    app = create_app(make_settings())
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    return TestClient(app)


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
    fake.add_role("x")
    login(anon, "pepe", "clave")
    assert call(anon, method, url, body).status_code == 403
    assert fake.roles == {1: {"nombre": "x", "descripcion": None}}  # no ha cambiado nada


# --- listado ---

def test_listado_vacio(admin):
    r = admin.get("/api/roles")
    assert r.status_code == 200 and r.json() == []


def test_listado_por_nombre_y_con_numero_de_usuarios(admin, fake):
    fake.add_role("Tutor", "Tutoriza prácticas", usuarios=["pepe", "ana"])
    fake.add_role("Alumno")
    assert admin.get("/api/roles").json() == [
        {"id": 2, "nombre": "Alumno", "descripcion": None, "num_usuarios": 0},
        {"id": 1, "nombre": "Tutor", "descripcion": "Tutoriza prácticas", "num_usuarios": 2},
    ]


# --- crear ---

def test_crear(admin):
    r = admin.post("/api/roles", json={"nombre": "Tutor", "descripcion": "Tutoriza prácticas"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "nombre": "Tutor", "descripcion": "Tutoriza prácticas", "num_usuarios": 0}
    assert len(admin.get("/api/roles").json()) == 1


def test_crear_limpia_espacios_y_descripcion_vacia_es_null(admin):
    r = admin.post("/api/roles", json={"nombre": "  Tutor  ", "descripcion": "   "})
    assert r.json()["nombre"] == "Tutor" and r.json()["descripcion"] is None


@pytest.mark.parametrize("body", [{}, {"nombre": ""}, {"nombre": "   "}, {"nombre": "x" * 101},
                                  {"nombre": "x", "descripcion": "x" * 501}])
def test_crear_datos_no_validos_es_422(admin, body):
    assert admin.post("/api/roles", json=body).status_code == 422


def test_crear_nombre_repetido_es_409(admin, fake):
    fake.add_role("Tutor")
    r = admin.post("/api/roles", json={"nombre": "Tutor"})
    assert r.status_code == 409 and r.json()["detail"] == "Ya existe un rol con ese nombre"


# --- editar ---

def test_editar_renombra_y_cambia_descripcion(admin, fake):
    rid = fake.add_role("Tutor", "vieja", usuarios=["pepe"])
    r = admin.put(f"/api/roles/{rid}", json={"nombre": "Tutor académico", "descripcion": "nueva"})
    assert r.status_code == 200
    assert r.json() == {"id": rid, "nombre": "Tutor académico", "descripcion": "nueva", "num_usuarios": 1}


def test_editar_manteniendo_el_mismo_nombre(admin, fake):
    """Guardar sin cambiar el nombre no choca consigo mismo."""
    rid = fake.add_role("Tutor")
    assert admin.put(f"/api/roles/{rid}", json={"nombre": "Tutor", "descripcion": "d"}).status_code == 200


def test_editar_con_nombre_de_otro_rol_es_409(admin, fake):
    fake.add_role("Tutor")
    rid = fake.add_role("Alumno")
    assert admin.put(f"/api/roles/{rid}", json={"nombre": "Tutor"}).status_code == 409
    assert fake.roles[rid]["nombre"] == "Alumno"


def test_editar_inexistente_es_404(admin):
    r = admin.put("/api/roles/99", json={"nombre": "x"})
    assert r.status_code == 404 and r.json()["detail"] == "El rol no existe"


# --- borrar ---

def test_borrar(admin, fake):
    rid = fake.add_role("Tutor")
    assert admin.delete(f"/api/roles/{rid}").status_code == 204
    assert admin.get("/api/roles").json() == []


def test_borrar_inexistente_es_404(admin):
    assert admin.delete("/api/roles/99").status_code == 404


@pytest.mark.parametrize("usuarios,texto", [(["pepe"], "1 usuario"), (["pepe", "ana"], "2 usuarios")])
def test_borrar_rol_con_usuarios_es_409_y_no_lo_borra(admin, fake, usuarios, texto):
    rid = fake.add_role("Tutor", usuarios=usuarios)
    r = admin.delete(f"/api/roles/{rid}")
    assert r.status_code == 409
    assert r.json()["detail"] == f"No se puede borrar: el rol está asignado a {texto}"
    assert rid in fake.roles


# --- usuarios de un rol ---

def test_usuarios_del_rol(admin, fake):
    rid = fake.add_role("Tutor", usuarios=["pepe", "ana"])
    fake.add_role("Alumno", usuarios=["admin"])
    r = admin.get(f"/api/roles/{rid}/usuarios")
    assert r.status_code == 200
    assert [u["username"] for u in r.json()] == ["ana", "pepe"]
    assert r.json()[1]["email"] == "pepe@example.com"


def test_usuarios_de_rol_sin_usuarios(admin, fake):
    rid = fake.add_role("Tutor")
    assert admin.get(f"/api/roles/{rid}/usuarios").json() == []


def test_usuarios_de_rol_inexistente_es_404(admin):
    assert admin.get("/api/roles/99/usuarios").status_code == 404
