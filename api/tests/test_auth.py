import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.main import create_app
from app.routers import auth
from app.security import hash_password

MSG = "Usuario o contraseña incorrectos"


@pytest.fixture
def client(monkeypatch):
    users = {"admin": hash_password("secreto")}
    app = create_app(Settings(postgres_db="t", postgres_user="t", postgres_password="t", app_secret="0123456789abcdef0123456789abcdef0123456789abcdef"))
    app.dependency_overrides[db.get_conn] = lambda: object()
    monkeypatch.setattr(auth, "find_password_hash", lambda conn, u: users.get(u))
    return TestClient(app)


def login(c, u="admin", p="secreto"):
    return c.post("/api/auth/login", json={"username": u, "password": p})


def test_login_ok_y_me(client):
    r = login(client)
    assert r.status_code == 200 and r.json() == {"username": "admin"}
    r = client.get("/api/auth/me")
    assert r.status_code == 200 and r.json() == {"username": "admin"}


def test_login_contrasena_mala(client):
    r = login(client, p="mala")
    assert r.status_code == 401 and r.json()["detail"] == MSG


def test_login_usuario_inexistente(client):
    r = login(client, u="nadie")
    assert r.status_code == 401 and r.json()["detail"] == MSG


def test_login_hash_corrupto_es_401(client, monkeypatch):  # Review Focus 3
    monkeypatch.setattr(auth, "find_password_hash", lambda conn, u: "no-es-bcrypt")
    assert login(client).status_code == 401


def test_login_campos_vacios(client):
    r = client.post("/api/auth/login", json={"username": "", "password": ""})
    assert r.status_code == 422


def test_logout(client):
    login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_me_sin_sesion(client):
    assert client.get("/api/auth/me").status_code == 401


def test_cookie_sin_secure(client):  # Review Focus 5
    cookie = login(client).headers["set-cookie"].lower()
    assert "secure" not in cookie and "httponly" in cookie


def test_bd_caida(client):  # Review Focus 4
    def caida():
        raise HTTPException(503, "Base de datos no disponible")

    client.app.dependency_overrides[db.get_conn] = caida
    r = login(client)
    assert r.status_code == 503 and r.json()["detail"] == "Base de datos no disponible"


def test_get_conn_operational_error_da_503(monkeypatch):
    def boom(**kw):
        raise db.psycopg.OperationalError("down")

    monkeypatch.setattr(db.psycopg, "connect", boom)
    monkeypatch.setattr(db, "get_settings", lambda: Settings(
        postgres_db="t", postgres_user="t", postgres_password="t", app_secret="0123456789abcdef0123456789abcdef0123456789abcdef"))
    with pytest.raises(HTTPException) as e:
        next(db.get_conn())
    assert e.value.status_code == 503 and e.value.detail == "Base de datos no disponible"
