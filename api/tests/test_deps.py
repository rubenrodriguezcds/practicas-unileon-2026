"""Tests de los permisos (app/deps.py) sin base de datos real.

Para qué: fijar que `require_admin` deja pasar solo al administrador (401 sin sesión, 403 a un
usuario normal) y que mira la bbdd en cada petición: quitar el permiso surte efecto al momento.

Cómo: una ruta de prueba protegida con `require_admin`, sobre la misma app y bbdd en memoria
que test_auth.py.
"""

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app import db
from app.deps import require_admin
from app.main import create_app
from tests.factories import FakeDB, make_settings, solve_captcha


@pytest.fixture
def fake():
    """Bbdd en memoria con admin/secreto (admin) y pepe/clave (usuario normal)."""
    f = FakeDB()
    f.users["pepe"] = f.user("clave")
    return f


@pytest.fixture
def client(fake, monkeypatch):
    """App con una ruta /api/solo-admin protegida y la bbdd sustituida por FakeDB."""
    app = create_app(make_settings())

    @app.get("/api/solo-admin")
    def solo_admin(username: str = Depends(require_admin)):
        return {"username": username}

    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    return TestClient(app)


def login(c, u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p, "altcha": solve_captcha(c.app.state.settings)})
    assert r.status_code == 200


def test_sin_sesion_es_401(client):
    assert client.get("/api/solo-admin").status_code == 401


def test_usuario_normal_es_403(client):
    login(client, "pepe", "clave")
    r = client.get("/api/solo-admin")
    assert r.status_code == 403 and r.json()["detail"] == "Solo el administrador puede hacer esto"


def test_admin_pasa(client):
    login(client, "admin", "secreto")
    r = client.get("/api/solo-admin")
    assert r.status_code == 200 and r.json() == {"username": "admin"}


def test_quitar_el_permiso_surte_efecto_al_momento(client, fake):
    """es_admin se lee de la bbdd en cada petición, no se guarda en la cookie."""
    login(client, "admin", "secreto")
    fake.users["admin"]["es_admin"] = False
    assert client.get("/api/solo-admin").status_code == 403


def test_usuario_borrado_es_401(client, fake):
    login(client, "pepe", "clave")
    del fake.users["pepe"]
    assert client.get("/api/solo-admin").status_code == 401
