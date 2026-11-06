"""Piezas comunes de los tests de la API: configuración de prueba, doble de bbdd y captcha.

Para qué: que cada fichero de tests no repita la misma configuración ni su propio doble de la
base de datos.

Qué hay:
  - `make_settings(**cambios)`: Settings válidos de prueba (captcha activo y barato de resolver).
  - `FakeDB`: sustituye las funciones de app/db.py por una bbdd en memoria que imita las
    transacciones (lo pendiente solo se guarda con commit y se descarta con rollback).
  - `solve_captcha(settings)`: resuelve un reto ALTCHA de verdad, como haría el navegador.
"""

import time

import altcha

from app import captcha, db
from app.config import Settings
from app.security import hash_password

SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef"
ALTCHA_KEY = "altcha-test-0123456789abcdef0123456789abcdef"


def make_settings(**changes) -> Settings:
    """Settings de prueba; `changes` sobrescribe cualquier campo."""
    base = dict(postgres_db="t", postgres_user="t", postgres_password="t", app_secret=SECRET,
                altcha_hmac_key=ALTCHA_KEY, altcha_cost=10)
    return Settings(**{**base, **changes})


def solve_captcha(s: Settings, expires_in: int = captcha.CHALLENGE_TTL) -> str:
    """Pide un reto, lo resuelve y devuelve el payload que enviaría el widget."""
    ch = altcha.create_challenge(captcha.ALGORITHM, s.altcha_cost, hmac_secret=s.altcha_hmac_key,
                                 expires_at=int(time.time()) + expires_in)
    return altcha.Payload(ch, altcha.solve_challenge(ch)).to_base64()


class FakeConn:
    """Conexión de mentira: registra commit/rollback para que FakeDB imite transacciones."""

    def __init__(self, fake):
        self.fake = fake

    def commit(self):
        self.fake.users.update(self.fake.staged)
        self.fake.staged.clear()

    def rollback(self):
        self.fake.staged.clear()


class FakeDB:
    """Bbdd en memoria con las mismas funciones que app/db.py (se instala con `install`)."""

    def __init__(self):
        # usuario → {"password_hash", "email", "reset_hash", "reset_expira", "es_admin"}
        self.users = {"admin": self.user("secreto", "admin@example.com", es_admin=True)}
        self.staged = {}  # cambios sin commit
        self.captchas = set()
        self.attempts = []  # (clave, instante)

    @staticmethod
    def user(password, email=None, es_admin=False):
        return {"password_hash": hash_password(password), "email": email, "reset_hash": None, "reset_expira": 0,
                "es_admin": es_admin}

    def install(self, monkeypatch):
        for name in ("find_user", "get_es_admin", "save_pending_password", "promote_pending_password",
                     "discard_pending_password", "mark_captcha_used", "count_reset_attempts", "add_reset_attempt"):
            monkeypatch.setattr(db, name, getattr(self, name))
        return FakeConn(self)

    def find_user(self, conn, username):
        u = self.users.get(username)
        if u is None:
            return None
        pending = u["reset_hash"] if u["reset_expira"] > time.time() else None
        return {"password_hash": u["password_hash"], "email": u["email"], "reset_hash": pending,
                "es_admin": u["es_admin"]}

    def get_es_admin(self, conn, username):
        u = self.users.get(username)
        return u["es_admin"] if u else None

    def save_pending_password(self, conn, username, hashed):
        self.staged[username] = {**self.users[username], "reset_hash": hashed, "reset_expira": time.time() + 3600}

    def promote_pending_password(self, conn, username):
        u = self.users[username]
        u.update(password_hash=u["reset_hash"], reset_hash=None, reset_expira=0)

    def discard_pending_password(self, conn, username):
        self.users[username].update(reset_hash=None, reset_expira=0)

    def mark_captcha_used(self, conn, signature, expires_at):
        if signature in self.captchas:
            return False
        self.captchas.add(signature)
        return True

    def count_reset_attempts(self, conn, keys):
        hour_ago = time.time() - 3600
        return max(sum(1 for k, t in self.attempts if k == key and t > hour_ago) for key in keys)

    def add_reset_attempt(self, conn, keys):
        self.attempts += [(k, time.time()) for k in keys]
