"""Piezas comunes de los tests de la API: configuración de prueba, doble de bbdd y captcha.

Para qué: que cada fichero de tests no repita la misma configuración ni su propio doble de la
base de datos.

Qué hay:
  - `make_settings(**cambios)`: Settings válidos de prueba (captcha activo y barato de resolver).
  - `FakeDB`: sustituye las funciones de app/db.py por una bbdd en memoria que imita las
    transacciones (lo pendiente solo se guarda con commit y se descarta con rollback).
  - `solve_captcha(settings)`: resuelve un reto ALTCHA de verdad, como haría el navegador.
"""

import re
import time
import unicodedata

import altcha

from app import captcha, db
from app.config import Settings
from app.security import hash_password

SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef"
ALTCHA_KEY = "altcha-test-0123456789abcdef0123456789abcdef"


def _sin_acentos(texto: str) -> str:
    """Como `unaccent` de Postgres: quita tildes y diéresis («MIGRACIÓN» → «MIGRACION»)."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


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
        self.next_user_id = 1
        # usuario → {"id", "password_hash", "email", "reset_hash", "reset_expira", "es_admin"}
        self.users = {"admin": self.user("secreto", "admin@example.com", es_admin=True)}
        self.staged = {}  # cambios sin commit
        self.captchas = set()
        self.attempts = []  # (clave, instante)
        self.roles = {}  # id → {"nombre", "descripcion"}
        self.asignaciones = set()  # (usuario, rol_id)
        self.next_role_id = 1
        self.proyectos = {}  # id → {"nombre", "tipo", "descripcion"}
        self.documentos = {}  # id → {"proyecto_id", "nombre", "contenido"}
        self.indexado = {}  # documento_id → {"estado", "error"}; sin entrada = pendiente
        self.fragmentos = {}  # documento_id → número de trozos
        self.resultados_busqueda = []  # lo que devuelve search_fragments
        self.busquedas = []  # (vector, texto, proyecto_id) de cada búsqueda
        self.validaciones = {}  # id → {"proyecto_id", "nombre", "tipo", "criterio", "orden"}
        self.resultados = {}  # validacion_id → {"estado", "explicacion", "resumen", "fragmentos", "ejecutada"}
        self.pruebas = {}  # fragmento_id → {"documento_id", "documento", "paginas", "texto"}
        self.next_validation_id = 1
        self.trozos = {}  # fragmento_id → {"proyecto_id", "documento_id", "texto"} (para los patrones)
        self.next_project_id = 1
        self.next_document_id = 1

    def user(self, password, email=None, es_admin=False):
        """Un usuario nuevo con id propio (como el SERIAL de la bbdd: no se reutilizan)."""
        uid, self.next_user_id = self.next_user_id, self.next_user_id + 1
        return {"id": uid, "password_hash": hash_password(password), "email": email, "reset_hash": None,
                "reset_expira": 0, "es_admin": es_admin}

    def _by_id(self, user_id):
        """(nombre, datos) del usuario con ese id, o (None, None)."""
        return next(((n, u) for n, u in self.users.items() if u["id"] == user_id), (None, None))

    def install(self, monkeypatch):
        for name in ("find_user", "get_session_user", "save_pending_password", "promote_pending_password",
                     "discard_pending_password", "mark_captcha_used", "count_reset_attempts", "add_reset_attempt",
                     "list_roles", "create_role", "update_role", "delete_role", "role_users",
                     "list_projects", "create_project", "get_project", "delete_project",
                     "update_project",
                     "add_document", "get_document", "delete_document",
                     "list_users", "get_user", "create_user", "update_user", "delete_users",
                     "add_user_role", "remove_user_role", "search_fragments",
                     "patron_valido", "list_validations", "create_validation", "update_validation",
                     "delete_validation", "get_validation", "run_pattern", "save_result", "document_counts",
                     "get_fragments"):
            monkeypatch.setattr(db, name, getattr(self, name))
        return FakeConn(self)

    def find_user(self, conn, username):
        u = self.users.get(username)
        if u is None:
            return None
        pending = u["reset_hash"] if u["reset_expira"] > time.time() else None
        return {"password_hash": u["password_hash"], "email": u["email"], "reset_hash": pending,
                "es_admin": u["es_admin"], "id": u["id"]}

    def get_session_user(self, conn, user_id):
        name, u = self._by_id(user_id)
        return {"id": user_id, "username": name, "es_admin": u["es_admin"]} if u else None

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
        return [{"id": self.users[u]["id"], "username": u, "email": self.users[u]["email"]}
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
                "documentos": [{"id": did, "nombre": d["nombre"], "tamano": len(d["contenido"]),
                                "indexado": {**self.indexado.get(did, {"estado": "pendiente", "error": None}),
                                             "fragmentos": self.fragmentos.get(did, 0)}}
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
        for vid in [v for v, val in self.validaciones.items() if val["proyecto_id"] == pid]:
            self.delete_validation(conn, vid)
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
    # --- usuarios: mismas reglas que la bbdd real (nombre único, el alta espera al commit,
    #     borrar un usuario borra sus asignaciones) ---

    def _usuario(self, name):
        u = self.users[name]
        return {"id": u["id"], "username": name, "email": u["email"], "es_admin": u["es_admin"]}

    def _num_roles(self, name):
        return sum(1 for n, _ in self.asignaciones if n == name)

    def list_users(self, conn):
        return [{**self._usuario(n), "num_roles": self._num_roles(n)} for n in sorted(self.users)]

    def get_user(self, conn, user_id):
        name, _ = self._by_id(user_id)
        if name is None:
            return None
        roles = sorted((self.roles[rid] | {"id": rid} for n, rid in self.asignaciones if n == name),
                       key=lambda r: r["nombre"])
        return {**self._usuario(name), "roles": [{"id": r["id"], "nombre": r["nombre"], "descripcion": r["descripcion"]}
                                                  for r in roles]}

    def create_user(self, conn, username, email, es_admin, password_hash):
        if username in self.users or username in self.staged:
            self.staged.clear()
            raise db.NombreDuplicado
        uid, self.next_user_id = self.next_user_id, self.next_user_id + 1
        self.staged[username] = {"id": uid, "password_hash": password_hash, "email": email, "reset_hash": None,
                                 "reset_expira": 0, "es_admin": es_admin}
        return {"id": uid, "username": username, "email": email, "es_admin": es_admin, "num_roles": 0}

    def update_user(self, conn, user_id, username, email, es_admin):
        old, u = self._by_id(user_id)
        if u is None:
            return None
        if username != old and username in self.users:
            raise db.NombreDuplicado
        del self.users[old]
        self.users[username] = {**u, "email": email, "es_admin": es_admin}
        self.asignaciones = {(username if n == old else n, rid) for n, rid in self.asignaciones}
        return self._usuario(username)

    def delete_users(self, conn, user_ids):
        names = [n for n, u in self.users.items() if u["id"] in user_ids]
        for n in names:
            del self.users[n]
        self.asignaciones = {(n, rid) for n, rid in self.asignaciones if n not in names}
        return len(names)

    def add_user_role(self, conn, user_id, rol_id):
        name, _ = self._by_id(user_id)
        if name is None or rol_id not in self.roles:
            return False
        self.asignaciones.add((name, rol_id))
        return True

    def remove_user_role(self, conn, user_id, rol_id):
        name, _ = self._by_id(user_id)
        self.asignaciones.discard((name, rol_id))

    # --- Búsqueda (el SQL de verdad se prueba con la bbdd real) ---

    def search_fragments(self, conn, vector, texto, proyecto_id, k=10):
        self.busquedas.append((vector, texto, proyecto_id))
        return self.resultados_busqueda[:k]


    # --- Validaciones ---

    def patron_valido(self, conn, patron):
        # Python no conoce \m, \M ni \y (inicio, fin y borde de palabra en Postgres): se traducen a \b.
        try:
            re.compile(re.sub(r"\\[mMy]", r"\\b", patron))
        except re.error as e:
            return str(e)
        return None

    def _validacion(self, vid):
        v = {"id": vid, **self.validaciones[vid], "resultado": None}
        if (r := self.resultados.get(vid)) is not None:
            v["resultado"] = {"estado": r["estado"], "explicacion": r["explicacion"], "resumen": r["resumen"],
                              "ejecutada": r["ejecutada"],
                              "pruebas": [self.pruebas[f] for f in r["fragmentos"] if f in self.pruebas]}
        return v

    def list_validations(self, conn, pid):
        if pid not in self.proyectos:
            return None
        vids = [v for v, val in self.validaciones.items() if val["proyecto_id"] == pid]
        return [self._validacion(v) for v in sorted(vids, key=lambda v: (self.validaciones[v]["orden"], v))]

    def create_validation(self, conn, pid, nombre, tipo, criterio):
        if pid not in self.proyectos:
            return None
        orden = max((v["orden"] for v in self.validaciones.values() if v["proyecto_id"] == pid), default=0) + 1
        vid, self.next_validation_id = self.next_validation_id, self.next_validation_id + 1
        self.validaciones[vid] = {"proyecto_id": pid, "nombre": nombre, "tipo": tipo, "criterio": criterio, "orden": orden}
        return self._validacion(vid)

    def update_validation(self, conn, vid, nombre, tipo, criterio):
        if vid not in self.validaciones:
            return None
        self.validaciones[vid].update(nombre=nombre, tipo=tipo, criterio=criterio)
        self.resultados.pop(vid, None)
        return self._validacion(vid)

    def delete_validation(self, conn, vid):
        self.resultados.pop(vid, None)
        return self.validaciones.pop(vid, None) is not None

    def add_fragment(self, pid, did, texto, paginas):
        """Atajo de los tests: un trozo indexado del documento `did` (y su prueba)."""
        fid = len(self.trozos) + 1
        self.trozos[fid] = {"proyecto_id": pid, "documento_id": did, "texto": texto}
        self.pruebas[fid] = {"documento_id": did, "documento": self.documentos[did]["nombre"],
                             "paginas": paginas, "texto": texto}
        return fid

    def get_validation(self, conn, vid):
        return self._validacion(vid) if vid in self.validaciones else None

    def run_pattern(self, conn, pid, patron):
        try:
            regex = re.compile(re.sub(r"\\[mMy]", r"\\b", _sin_acentos(patron)), re.IGNORECASE)
        except re.error as e:
            raise db.PatronNoValido(str(e)) from None
        coinciden = [fid for fid, t in sorted(self.trozos.items(), key=lambda x: (x[1]["documento_id"], x[0]))
                     if t["proyecto_id"] == pid and regex.search(_sin_acentos(t["texto"]))]
        primeros = list({self.trozos[f]["documento_id"]: f for f in reversed(coinciden)}.values())[::-1]
        return {"trozos": len(coinciden), "documentos": len(primeros), "fragmentos": primeros,
                **self.document_counts(conn, pid)}

    def document_counts(self, conn, pid):
        docs = [did for did, d in self.documentos.items() if d["proyecto_id"] == pid]
        hechos = [did for did in docs if self.indexado.get(did, {}).get("estado") == "hecho"]
        return {"indexados": len(hechos), "pendientes": len(docs) - len(hechos)}

    def get_fragments(self, conn, ids):
        return [{k: self.pruebas[i][k] for k in ("documento", "paginas", "texto")} for i in ids if i in self.pruebas]

    def save_result(self, conn, vid, estado, explicacion, fragmentos, resumen=None):
        self.resultados[vid] = {"estado": estado, "explicacion": explicacion, "resumen": resumen,
                                "fragmentos": list(fragmentos), "ejecutada": "2026-11-27T12:00:00+00:00"}
