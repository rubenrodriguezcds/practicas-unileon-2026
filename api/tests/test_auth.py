"""Tests de /api/auth (login, logout, me) sin base de datos real.

Para qué: fijar el contrato que usa el frontend (códigos, mensajes y cookie) y los casos
delicados: mismo 401 para usuario inexistente y contraseña mala, hash corrupto → 401, cookie
HttpOnly sin Secure, bbdd caída → 503 y captcha obligatorio, caducado o reutilizado → 400.

Cómo: la conexión a Postgres se sustituye por un doble (dependency override) y las consultas
por la bbdd en memoria de tests/factories.py, así que se ejecutan en milisegundos y sin Docker.
El captcha se resuelve de verdad con la librería ALTCHA, como haría el navegador.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha

MSG = "Usuario o contraseña incorrectos"
CAPTCHA_MSG = "Verificación anti-bot no válida"


@pytest.fixture
def fake(monkeypatch):
    """Bbdd en memoria con admin/secreto."""
    return FakeDB()


@pytest.fixture
def client(fake, monkeypatch):
    """App con la bbdd sustituida por FakeDB."""
    app = create_app(make_settings())
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    return TestClient(app)


def login(c, u="admin", p="secreto", altcha="resolver"):
    """Atajo para POST /api/auth/login; por defecto con un captcha recién resuelto."""
    if altcha == "resolver":
        altcha = solve_captcha(c.app.state.settings)
    return c.post("/api/auth/login", json={"username": u, "password": p, "altcha": altcha})


def test_login_ok_y_me(client):
    """Un login correcto (con captcha válido) deja la sesión activa y /me devuelve el usuario."""
    r = login(client)
    assert r.status_code == 200 and r.json() == {"username": "admin", "es_admin": True}
    r = client.get("/api/auth/me")
    assert r.status_code == 200 and r.json() == {"username": "admin", "es_admin": True}


def test_login_y_me_de_usuario_no_admin(client, fake):
    """Un usuario normal entra igual, pero con es_admin=False."""
    fake.users["pepe"] = fake.user("clave")
    assert login(client, u="pepe", p="clave").json() == {"username": "pepe", "es_admin": False}
    assert client.get("/api/auth/me").json() == {"username": "pepe", "es_admin": False}


def test_renombrar_al_usuario_no_cierra_su_sesion(client, fake):
    """La sesión guarda el id: si el administrador renombra al usuario, sigue dentro con el nombre nuevo."""
    fake.users["pepe"] = fake.user("clave")
    login(client, u="pepe", p="clave")
    fake.users["jose"] = fake.users.pop("pepe")
    assert client.get("/api/auth/me").json() == {"username": "jose", "es_admin": False}


def test_me_de_usuario_borrado_cierra_la_sesion(client, fake):
    """Si el usuario de la sesión ya no existe, /me da 401 y la sesión se borra."""
    fake.users["pepe"] = fake.user("clave")
    login(client, u="pepe", p="clave")
    del fake.users["pepe"]
    assert client.get("/api/auth/me").status_code == 401
    fake.users["pepe"] = fake.user("clave")  # aunque vuelva a existir, la sesión ya no vale
    assert client.get("/api/auth/me").status_code == 401


def test_login_contrasena_mala(client):
    """Contraseña errónea da 401 con el mensaje genérico."""
    r = login(client, p="mala")
    assert r.status_code == 401 and r.json()["detail"] == MSG


def test_login_usuario_inexistente(client):
    """Usuario inexistente da el mismo 401 y mensaje (no revela si existe)."""
    r = login(client, u="nadie")
    assert r.status_code == 401 and r.json()["detail"] == MSG


def test_login_hash_corrupto_es_401(client, fake):
    """Un hash corrupto en la bbdd debe dar 401, no 500."""
    fake.users["admin"]["password_hash"] = "no-es-bcrypt"
    assert login(client).status_code == 401


def test_login_campos_vacios(client):
    """Campos vacíos se rechazan con 422 antes de consultar la bbdd."""
    r = client.post("/api/auth/login", json={"username": "", "password": ""})
    assert r.status_code == 422


def test_logout(client):
    """Logout responde 204 e invalida la sesión (/me pasa a 401)."""
    login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_me_sin_sesion(client):
    """/me sin cookie de sesión da 401."""
    assert client.get("/api/auth/me").status_code == 401


def test_cookie_sin_secure(client):
    """La cookie es HttpOnly y sin Secure: en HTTP plano un Secure no se guardaría."""
    cookie = login(client).headers["set-cookie"].lower()
    assert "secure" not in cookie and "httponly" in cookie


def test_bd_caida(client):
    """Si la dependencia de bbdd falla, el login responde 503 con mensaje claro."""
    def caida():
        raise HTTPException(503, "Base de datos no disponible")

    client.app.dependency_overrides[db.get_conn] = caida
    r = login(client)
    assert r.status_code == 503 and r.json()["detail"] == "Base de datos no disponible"


def test_get_conn_operational_error_da_503(monkeypatch):
    """get_conn traduce un OperationalError al conectar en HTTPException 503."""
    def boom(**kw):
        raise db.psycopg.OperationalError("down")

    monkeypatch.setattr(db.psycopg, "connect", boom)
    monkeypatch.setattr(db, "get_settings", make_settings)
    with pytest.raises(HTTPException) as e:
        next(db.get_conn())
    assert e.value.status_code == 503 and e.value.detail == "Base de datos no disponible"


# --- captcha en el login ---

@pytest.mark.parametrize("altcha", [None, "", "basura", "eyJmb28iOiAxfQ=="])
def test_login_sin_captcha_valido_es_400(client, altcha):
    """Sin captcha, o con uno mal formado, el login se rechaza antes de mirar la contraseña."""
    r = login(client, altcha=altcha)
    assert r.status_code == 400 and r.json()["detail"] == CAPTCHA_MSG


def test_login_captcha_reutilizado_es_400(client):
    """Un reto ya usado no vale otra vez, aunque el primer intento fallara."""
    payload = solve_captcha(client.app.state.settings)
    assert login(client, p="mala", altcha=payload).status_code == 401
    r = login(client, altcha=payload)
    assert r.status_code == 400 and r.json()["detail"] == CAPTCHA_MSG


def test_login_captcha_caducado_es_400(client):
    """Un reto caducado se rechaza."""
    payload = solve_captcha(client.app.state.settings, expires_in=-1)
    assert login(client, altcha=payload).status_code == 400


def test_login_captcha_firmado_con_otra_clave_es_400(client):
    """Un reto que no ha firmado esta API (otra clave) se rechaza."""
    payload = solve_captcha(make_settings(altcha_hmac_key="otra-clave-" + "x" * 32))
    assert login(client, altcha=payload).status_code == 400


def test_login_con_captcha_desactivado(fake, monkeypatch):
    """Con ALTCHA_ENABLED=false el login funciona sin captcha (tests y desarrollo)."""
    app = create_app(make_settings(altcha_enabled=False, altcha_hmac_key=""))
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    assert login(TestClient(app), altcha=None).status_code == 200


def test_get_captcha_entrega_reto_firmado(client):
    """GET /api/captcha devuelve un reto con firma y caducidad, sin caché."""
    r = client.get("/api/captcha")
    body = r.json()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert body["signature"] and body["parameters"]["expiresAt"]
