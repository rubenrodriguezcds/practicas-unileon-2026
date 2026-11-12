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
        self.roles = {}  # id → {"nombre", "descripcion"}
        self.asignaciones = set()  # (usuario, rol_id)
        self.next_role_id = 1
        self.proyectos = {}  # id → {"nombre", "tipo", "descripcion"}
        self.documentos = {}  # id → {"proyecto_id", "nombre", "contenido"}
        self.next_project_id = 1
        self.next_document_id = 1

    @staticmethod
    def user(password, email=None, es_admin=False):
        return {"password_hash": hash_password(password), "email": email, "reset_hash": None, "reset_expira": 0,
                "es_admin": es_admin}

    def install(self, monkeypatch):
        for name in ("find_user", "get_es_admin", "save_pending_password", "promote_pending_password",
                     "discard_pending_password", "mark_captcha_used", "count_reset_attempts", "add_reset_attempt",
                     "list_roles", "create_role", "update_role", "delete_role", "role_users",
                     "list_projects", "create_project", "get_project", "delete_project",
                     "update_project",
                     "add_document", "get_document", "delete_document"):
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

    # --- roles: mismas reglas que la bbdd real (nombre único, no borrar un rol con usuarios) ---

    def add_role(self, nombre, descripcion=None, usuarios=()):
        """Atajo de los tests: crea un rol ya asignado a `usuarios` y devuelve su id."""
        rol_id = self.create_role(None, nombre, descripcion)["id"]
        self.asignaciones |= {(u, rol_id) for u in usuarios}
        return rol_id

    def _rol(self, rol_id):
        r = self.roles[rol_id]
        n = sum(1 for _, rid in self.asignaciones if rid == rol_id)
        return {"id": rol_id, "nombre": r["nombre"], "descripcion": r["descripcion"], "num_usuarios": n}

    def _check_nombre(self, nombre, rol_id=None):
        if any(r["nombre"] == nombre and rid != rol_id for rid, r in self.roles.items()):
            raise db.NombreDuplicado

    def list_roles(self, conn):
        return sorted((self._rol(rid) for rid in self.roles), key=lambda r: r["nombre"])

    def create_role(self, conn, nombre, descripcion):
        self._check_nombre(nombre)
        rol_id, self.next_role_id = self.next_role_id, self.next_role_id + 1
        self.roles[rol_id] = {"nombre": nombre, "descripcion": descripcion}
        return self._rol(rol_id)

    def update_role(self, conn, rol_id, nombre, descripcion):
        if rol_id not in self.roles:
            return None
        self._check_nombre(nombre, rol_id)
        self.roles[rol_id] = {"nombre": nombre, "descripcion": descripcion}
        return self._rol(rol_id)

    def delete_role(self, conn, rol_id):
        if rol_id not in self.roles:
            return None
        n = self._rol(rol_id)["num_usuarios"]
        if n == 0:
            del self.roles[rol_id]
        return n

    def role_users(self, conn, rol_id):
        if rol_id not in self.roles:
            return None
        ids = {u: i for i, u in enumerate(self.users, 1)}
        return [{"id": ids[u], "username": u, "email": self.users[u]["email"]}
                for u in sorted(u for u, rid in self.asignaciones if rid == rol_id)]

    # --- proyectos (issue #7): mismas reglas que la bbdd real (nombres únicos sin mayúsculas, cascada) ---

    def add_project(self, nombre, docs=None, tipo=None, descripcion=None):
        """Atajo de los tests: crea un proyecto con documentos {nombre: bytes} y devuelve su id."""
        pid = self.create_project(None, nombre, tipo, descripcion)["id"]
        for doc_nombre, contenido in (docs or {}).items():
            self.add_document(None, pid, doc_nombre, contenido)
        return pid

    def _docs_de(self, pid):
        return sorted(((did, d) for did, d in self.documentos.items() if d["proyecto_id"] == pid),
                      key=lambda x: x[1]["nombre"].lower())

    def _proyecto(self, pid):
        p = self.proyectos[pid]
        return {"id": pid, **p, "num_documentos": len(self._docs_de(pid))}

    def list_projects(self, conn):
        return sorted((self._proyecto(pid) for pid in self.proyectos), key=lambda p: p["nombre"].lower())

    def create_project(self, conn, nombre, tipo, descripcion):
        if any(p["nombre"].lower() == nombre.lower() for p in self.proyectos.values()):
            raise db.NombreDuplicado
        pid, self.next_project_id = self.next_project_id, self.next_project_id + 1
        self.proyectos[pid] = {"nombre": nombre, "tipo": tipo, "descripcion": descripcion}
        return self._proyecto(pid)

    def get_project(self, conn, pid):
        if pid not in self.proyectos:
            return None
        return {"id": pid, **self.proyectos[pid],
                "documentos": [{"id": did, "nombre": d["nombre"], "tamano": len(d["contenido"])}
                               for did, d in self._docs_de(pid)]}

    def update_project(self, conn, pid, nombre, tipo, descripcion):
        if pid not in self.proyectos:
            return None
        if any(p["nombre"].lower() == nombre.lower() for i, p in self.proyectos.items() if i != pid):
            raise db.NombreDuplicado
        self.proyectos[pid] = {"nombre": nombre, "tipo": tipo, "descripcion": descripcion}
        return self._proyecto(pid)

    def delete_project(self, conn, pid):
        if self.proyectos.pop(pid, None) is None:
            return False
        self.documentos = {did: d for did, d in self.documentos.items() if d["proyecto_id"] != pid}  # cascada
        return True

    def add_document(self, conn, pid, nombre, contenido):
        if pid not in self.proyectos:
            return None
        if any(d["nombre"].lower() == nombre.lower() for _, d in self._docs_de(pid)):
            raise db.NombreDuplicado
        did, self.next_document_id = self.next_document_id, self.next_document_id + 1
        self.documentos[did] = {"proyecto_id": pid, "nombre": nombre, "contenido": contenido}
        return {"id": did, "nombre": nombre, "tamano": len(contenido)}

    def get_document(self, conn, did):
        d = self.documentos.get(did)
        return {"nombre": d["nombre"], "contenido": d["contenido"]} if d else None

    def delete_document(self, conn, did):
        return self.documentos.pop(did, None) is not None
