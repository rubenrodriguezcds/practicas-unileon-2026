"""Tests de POST /api/auth/reset (reseteo de contraseña) sin bbdd ni servidor de correo reales.

Para qué: fijar lo que hace seguro el reseteo:
  - la contraseña nueva llega por correo, hasheada con bcrypt como el resto;
  - la vieja sigue valiendo hasta que se entra con la nueva (nadie puede dejar a otro sin acceso);
  - misma respuesta para usuario inexistente, sin email, válido o fallo del correo;
  - si el correo falla, rollback: la contraseña no cambia;
  - límite de intentos por usuario y por IP (429) y captcha obligatorio.

Cómo: FakeDB (tests/factories.py) hace de bbdd y `mailer.send_mail` se sustituye por una
función que guarda los correos en una lista.
"""

import re
import smtplib
import time

import pytest
from fastapi.testclient import TestClient

from app import db, mailer
from app.main import create_app
from app.routers.auth import RESET_MSG
from app.security import verify_password
from tests.factories import FakeDB, make_settings, solve_captcha


@pytest.fixture
def fake():
    """Bbdd en memoria: admin/secreto con email, y «sinmail» sin email."""
    f = FakeDB()
    f.users["sinmail"] = f.user("otra")
    return f


@pytest.fixture
def sent(monkeypatch):
    """Correos «enviados»: lista de (destino, asunto, cuerpo)."""
    box = []
    monkeypatch.setattr(mailer, "send_mail", lambda s, to, subject, body: box.append((to, subject, body)))
    return box


def make_client(fake, monkeypatch, **settings):
    app = create_app(make_settings(**settings))
    conn = fake.install(monkeypatch)
    app.dependency_overrides[db.get_conn] = lambda: conn
    return TestClient(app)


@pytest.fixture
def client(fake, monkeypatch):
    return make_client(fake, monkeypatch)


def reset(c, u="admin", altcha="resolver"):
    if altcha == "resolver":
        altcha = solve_captcha(c.app.state.settings)
    return c.post("/api/auth/reset", json={"username": u, "altcha": altcha})


def login(c, u, p):
    return c.post("/api/auth/login", json={"username": u, "password": p, "altcha": solve_captcha(c.app.state.settings)})


def new_password(mail_body):
    """Saca la contraseña del cuerpo del correo (va sola en su línea, sangrada)."""
    return re.search(r"^    (\S+)$", mail_body, re.M).group(1)


def test_reset_envia_correo_y_guarda_hash_bcrypt(client, fake, sent):
    """Usuario válido: 202 genérico, correo a su email y contraseña pendiente con bcrypt."""
    r = reset(client)
    assert r.status_code == 202 and r.json() == {"detail": RESET_MSG}
    (to, _, body), = sent
    assert to == "admin@example.com"
    pending = fake.users["admin"]["reset_hash"]
    assert pending.startswith("$2") and verify_password(new_password(body), pending)


def test_la_vieja_sigue_valiendo_hasta_entrar_con_la_nueva(client, sent):
    """Tras entrar con la nueva, la vieja ya no vale (y la nueva sigue valiendo)."""
    reset(client)
    nueva = new_password(sent[0][2])
    assert login(client, "admin", nueva).status_code == 200
    assert login(client, "admin", "secreto").status_code == 401
    assert login(client, "admin", nueva).status_code == 200


def test_entrar_con_la_vieja_descarta_la_pendiente(client, sent):
    """Si el dueño entra con su contraseña de siempre, la pendiente deja de valer."""
    reset(client)
    nueva = new_password(sent[0][2])
    assert login(client, "admin", "secreto").status_code == 200
    assert login(client, "admin", nueva).status_code == 401


def test_pendiente_caducada_no_vale(client, fake, sent):
    """Pasada la hora, la contraseña del correo ya no sirve."""
    reset(client)
    fake.users["admin"]["reset_expira"] = time.time() - 1
    assert login(client, "admin", new_password(sent[0][2])).status_code == 401


@pytest.mark.parametrize("username", ["admin", "nadie", "sinmail"])
def test_misma_respuesta_exista_o_no(client, sent, username):
    """Válido, inexistente y sin email responden exactamente igual."""
    r = reset(client, username)
    assert r.status_code == 202 and r.json() == {"detail": RESET_MSG}


def test_sin_email_o_inexistente_no_envia_nada(client, fake, sent):
    reset(client, "nadie")
    reset(client, "sinmail")
    assert sent == [] and fake.users["sinmail"]["reset_hash"] is None


@pytest.mark.parametrize("error", [smtplib.SMTPException("rechazado"), TimeoutError("sin respuesta")])
def test_fallo_de_correo_hace_rollback_y_responde_igual(client, fake, monkeypatch, caplog, error):
    """Si el correo falla: misma respuesta, error en el log y la contraseña no cambia."""
    def falla(*a):
        raise error

    monkeypatch.setattr(mailer, "send_mail", falla)
    r = reset(client)
    assert r.status_code == 202 and r.json() == {"detail": RESET_MSG}
    assert fake.users["admin"]["reset_hash"] is None and fake.staged == {}
    assert "No se pudo enviar el correo de reseteo" in caplog.text
    assert login(client, "admin", "secreto").status_code == 200


def test_rate_limit_por_usuario(fake, monkeypatch, sent):
    """Superado el límite por hora para un usuario → 429, aunque cambie la IP."""
    c = make_client(fake, monkeypatch, reset_max_por_hora=2)
    assert [reset(c).status_code for _ in range(3)] == [202, 202, 429]
    assert reset(c).json()["detail"] == "Demasiados intentos. Prueba más tarde."
    assert len(sent) == 2


def test_rate_limit_por_ip(fake, monkeypatch, sent):
    """Superado el límite desde una IP → 429 aunque se vaya cambiando de usuario."""
    c = make_client(fake, monkeypatch, reset_max_por_hora=2)
    assert [reset(c, u).status_code for u in ("a", "b", "c")] == [202, 202, 429]


def test_reset_sin_captcha_es_400(client, sent):
    assert reset(client, altcha=None).status_code == 400
    assert sent == []


def test_reset_captcha_reutilizado_es_400(client, sent):
    payload = solve_captcha(client.app.state.settings)
    assert reset(client, altcha=payload).status_code == 202
    assert reset(client, altcha=payload).status_code == 400


def test_reset_usuario_vacio_es_422(client):
    assert client.post("/api/auth/reset", json={"username": ""}).status_code == 422
