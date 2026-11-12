"""Tests de /api/usuarios (issue #6) sin base de datos real ni correo real.

Para qué: fijar el contrato que usa la pantalla de usuarios (códigos, mensajes y forma de los
datos) y las reglas de la issue y de seguridad: solo el administrador entra (401/403 en TODOS los
endpoints), el nombre es único (409), la contraseña del alta llega por correo y sirve para entrar,
si el correo falla el usuario no se crea (502), y el administrador no puede borrarse ni quitarse
su propio permiso (409).

Cómo: la misma app y bbdd en memoria (tests/factories.py) que test_auth.py; el envío de correo se
sustituye por una lista, como en test_reset.py.
"""

import re
import smtplib

import pytest
from fastapi.testclient import TestClient

from app import db, mailer
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha

ENDPOINTS = [
    ("get", "/api/usuarios", None),
    ("get", "/api/usuarios/2", None),
    ("post", "/api/usuarios", {"username": "nuevo", "email": "n@example.com"}),
    ("put", "/api/usuarios/2", {"username": "x", "es_admin": False}),
    ("delete", "/api/usuarios/2", None),
    ("post", "/api/usuarios/borrar", {"ids": [2]}),
    ("put", "/api/usuarios/2/roles/1", None),
    ("delete", "/api/usuarios/2/roles/1", None),
]


@pytest.fixture
def fake():
    """admin/secreto (id 1, admin), pepe/clave (id 2) y ana/clave (id 3)."""
    f = FakeDB()
    f.users["pepe"] = f.user("clave", "pepe@example.com")
    f.users["ana"] = f.user("clave")
    return f


@pytest.fixture
def sent(monkeypatch):
    """Correos «enviados»: lista de (destino, asunto, cuerpo)."""
    box = []
    monkeypatch.setattr(mailer, "send_mail", lambda s, to, subject, body: box.append((to, subject, body)))
    return box


@pytest.fixture
def anon(fake, monkeypatch, sent):
    app = create_app(make_settings())
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    return TestClient(app)


def login(c, u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p, "altcha": solve_captcha(c.app.state.settings)})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def admin(anon):
    return login(anon, "admin", "secreto")


# --- permisos ---

@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_sin_sesion_es_401(anon, method, url, body):
    assert anon.request(method, url, json=body).status_code == 401


@pytest.mark.parametrize("method,url,body", ENDPOINTS)
def test_usuario_normal_es_403(anon, fake, sent, method, url, body):
    fake.add_role("Tutor")
    login(anon, "pepe", "clave")
    antes = {n: dict(u) for n, u in fake.users.items()}
    assert anon.request(method, url, json=body).status_code == 403
    assert fake.users == antes and sent == []  # no ha cambiado nada


# --- listado y detalle ---

def test_listado_por_nombre_con_numero_de_roles(admin, fake):
    fake.add_role("Tutor", usuarios=["pepe"])
    fake.add_role("Alumno", usuarios=["pepe"])
    assert admin.get("/api/usuarios").json() == [
        {"id": 1, "username": "admin", "email": "admin@example.com", "es_admin": True, "num_roles": 0},
        {"id": 3, "username": "ana", "email": None, "es_admin": False, "num_roles": 0},
        {"id": 2, "username": "pepe", "email": "pepe@example.com", "es_admin": False, "num_roles": 2},
    ]


def test_detalle_con_roles_por_nombre(admin, fake):
    fake.add_role("Tutor", "Tutoriza", usuarios=["pepe"])
    fake.add_role("Alumno", usuarios=["pepe"])
    r = admin.get("/api/usuarios/2")
    assert r.status_code == 200
    assert r.json() == {"id": 2, "username": "pepe", "email": "pepe@example.com", "es_admin": False, "roles": [
        {"id": 2, "nombre": "Alumno", "descripcion": None},
        {"id": 1, "nombre": "Tutor", "descripcion": "Tutoriza"},
    ]}


def test_detalle_inexistente_es_404(admin):
    r = admin.get("/api/usuarios/99")
    assert r.status_code == 404 and r.json()["detail"] == "El usuario no existe"


# --- crear ---

def test_crear_envia_la_contrasena_y_sirve_para_entrar(admin, sent):
    r = admin.post("/api/usuarios", json={"username": "lucia", "email": " lucia@example.com ", "es_admin": True})
    assert r.status_code == 201
    assert r.json() == {"id": 4, "username": "lucia", "email": "lucia@example.com", "es_admin": True, "num_roles": 0}
    [(to, subject, body)] = sent
    assert to == "lucia@example.com" and subject == "Tu cuenta en el gestor documental"
    password = re.search(r"Contraseña: (\S+)", body).group(1)
    assert len(password) >= 16
    admin.post("/api/auth/logout")
    login(admin, "lucia", password)
    assert admin.get("/api/auth/me").json() == {"username": "lucia", "es_admin": True}


def test_crear_por_defecto_no_es_admin(admin):
    r = admin.post("/api/usuarios", json={"username": "lucia", "email": "l@example.com"})
    assert r.json()["es_admin"] is False


def test_crear_nombre_repetido_es_409_y_no_envia_correo(admin, sent):
    r = admin.post("/api/usuarios", json={"username": "pepe", "email": "otro@example.com"})
    assert r.status_code == 409 and r.json()["detail"] == "Ya existe un usuario con ese nombre"
    assert sent == []


@pytest.mark.parametrize("body", [
    {"username": "lucia"},                                  # sin email
    {"username": "lucia", "email": "no-es-un-email"},
    {"username": "", "email": "l@example.com"},
    {"username": "con espacio", "email": "l@example.com"},
    {"username": "x" * 51, "email": "l@example.com"},
])
def test_crear_datos_no_validos_es_422(admin, sent, body):
    assert admin.post("/api/usuarios", json=body).status_code == 422
    assert sent == []


def test_si_el_correo_falla_el_usuario_no_se_crea(admin, fake, monkeypatch):
    def falla(*a):
        raise smtplib.SMTPException("caído")

    monkeypatch.setattr(mailer, "send_mail", falla)
    r = admin.post("/api/usuarios", json={"username": "lucia", "email": "l@example.com"})
    assert r.status_code == 502 and "no se ha creado" in r.json()["detail"]
    assert "lucia" not in fake.users
    assert [u["username"] for u in admin.get("/api/usuarios").json()] == ["admin", "ana", "pepe"]


# --- editar ---

def test_editar_renombra_cambia_email_y_hace_admin(admin, fake):
    fake.add_role("Tutor", usuarios=["pepe"])
    r = admin.put("/api/usuarios/2", json={"username": "jose", "email": "jose@example.com", "es_admin": True})
    assert r.status_code == 200
    assert r.json() == {"id": 2, "username": "jose", "email": "jose@example.com", "es_admin": True}
    assert admin.get("/api/usuarios/2").json()["roles"][0]["nombre"] == "Tutor"  # conserva sus roles


def test_editar_email_vacio_lo_deja_sin_email(admin):
    r = admin.put("/api/usuarios/2", json={"username": "pepe", "email": "  ", "es_admin": False})
    assert r.status_code == 200 and r.json()["email"] is None


def test_editar_con_nombre_de_otro_es_409(admin, fake):
    assert admin.put("/api/usuarios/2", json={"username": "ana", "es_admin": False}).status_code == 409
    assert "pepe" in fake.users


def test_editar_sin_es_admin_es_422(admin, fake):
    """es_admin es obligatorio al editar, para no quitar el permiso a nadie por omisión."""
    fake.users["pepe"]["es_admin"] = True
    assert admin.put("/api/usuarios/2", json={"username": "pepe"}).status_code == 422
    assert fake.users["pepe"]["es_admin"] is True


def test_editar_inexistente_es_404(admin):
    assert admin.put("/api/usuarios/99", json={"username": "x", "es_admin": False}).status_code == 404


def test_no_puedes_quitarte_tu_propio_permiso(admin, fake):
    r = admin.put("/api/usuarios/1", json={"username": "admin", "email": "admin@example.com", "es_admin": False})
    assert r.status_code == 409 and r.json()["detail"] == "No puedes quitarte a ti mismo el permiso de administrador"
    assert fake.users["admin"]["es_admin"] is True


def test_renombrarte_a_ti_mismo_no_cierra_tu_sesion(admin):
    r = admin.put("/api/usuarios/1", json={"username": "jefa", "email": "admin@example.com", "es_admin": True})
    assert r.status_code == 200
    assert admin.get("/api/auth/me").json() == {"username": "jefa", "es_admin": True}


def test_quitar_el_permiso_a_otro_admin_surte_efecto_al_momento(anon, fake):
    fake.users["pepe"]["es_admin"] = True
    otro = TestClient(anon.app)
    login(otro, "pepe", "clave")
    login(anon, "admin", "secreto")
    assert anon.put("/api/usuarios/2", json={"username": "pepe", "es_admin": False}).status_code == 200
    assert otro.get("/api/usuarios").status_code == 403


# --- borrar ---

def test_borrar_uno_le_quita_tambien_los_roles(admin, fake):
    fake.add_role("Tutor", usuarios=["pepe", "ana"])
    assert admin.delete("/api/usuarios/2").status_code == 204
    assert "pepe" not in fake.users
    assert fake.asignaciones == {("ana", 1)}


def test_borrar_inexistente_es_404(admin):
    assert admin.delete("/api/usuarios/99").status_code == 404


def test_no_puedes_borrarte_a_ti_mismo(admin, fake):
    r = admin.delete("/api/usuarios/1")
    assert r.status_code == 409 and r.json()["detail"] == "No puedes borrar tu propio usuario"
    assert "admin" in fake.users


def test_borrar_en_lote(admin, fake):
    r = admin.post("/api/usuarios/borrar", json={"ids": [2, 3, 99, 2]})
    assert r.status_code == 200 and r.json() == {"borrados": 2}
    assert list(fake.users) == ["admin"]


def test_lote_que_te_incluye_no_borra_ninguno(admin, fake):
    r = admin.post("/api/usuarios/borrar", json={"ids": [2, 1]})
    assert r.status_code == 409
    assert set(fake.users) == {"admin", "pepe", "ana"}


def test_lote_vacio_es_422(admin):
    assert admin.post("/api/usuarios/borrar", json={"ids": []}).status_code == 422


# --- roles del usuario ---

def test_asociar_y_quitar_rol(admin, fake):
    rid = fake.add_role("Tutor")
    assert admin.put(f"/api/usuarios/2/roles/{rid}").status_code == 204
    assert admin.put(f"/api/usuarios/2/roles/{rid}").status_code == 204  # repetir no cambia nada
    assert [r["nombre"] for r in admin.get("/api/usuarios/2").json()["roles"]] == ["Tutor"]
    assert admin.delete(f"/api/usuarios/2/roles/{rid}").status_code == 204
    assert admin.get("/api/usuarios/2").json()["roles"] == []
    assert admin.delete(f"/api/usuarios/2/roles/{rid}").status_code == 204  # quitar otra vez, igual


@pytest.mark.parametrize("url", ["/api/usuarios/99/roles/1", "/api/usuarios/2/roles/99"])
def test_asociar_con_usuario_o_rol_inexistente_es_404(admin, fake, url):
    fake.add_role("Tutor")
    r = admin.put(url)
    assert r.status_code == 404 and r.json()["detail"] == "El usuario o el rol no existe"


def test_el_listado_de_roles_refleja_las_asociaciones(admin, fake):
    rid = fake.add_role("Tutor")
    admin.put(f"/api/usuarios/2/roles/{rid}")
    assert admin.get("/api/roles").json()[0]["num_usuarios"] == 1
