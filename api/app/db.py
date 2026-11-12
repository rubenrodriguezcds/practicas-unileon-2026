"""Acceso a la base de datos PostgreSQL.

Para qué: abre una conexión por petición HTTP y contiene las consultas SQL de la app.

Por qué existe: es el ÚNICO sitio que habla SQL. Los endpoints no saben nada de psycopg ni de
tablas; solo piden datos con funciones como `find_user`. Si mañana se cambia a un ORM
(SQLAlchemy) o se añaden tablas, el cambio queda aquí.

Quién lo usa: routers/auth.py (a través de la dependencia de FastAPI `Depends(get_conn)`),
deps.py (permisos), captcha.py y migrations.py (que usa `connect` al arrancar).

Notas:
  - Si Postgres no responde, se devuelve 503 «Base de datos no disponible» (y se deja en el log)
    en vez de un 500 genérico, para que el usuario sepa que el problema no es su contraseña.
  - La conexión se cierra siempre al acabar la petición, también si hay errores.
  - Dentro de Docker se conecta a `db:5432` (red interna), no al 1521 publicado al host.
"""

import logging

import psycopg
from fastapi import HTTPException

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def connect(s: Settings, **kwargs):
    """Abre una conexión con los datos de `s` (kwargs extra, p. ej. autocommit, van a psycopg)."""
    return psycopg.connect(
        host=s.db_host, port=s.db_port, dbname=s.postgres_db,
        user=s.postgres_user, password=s.postgres_password, connect_timeout=3, **kwargs,
    )


def get_conn():
    """Dependencia FastAPI: abre una conexión por petición y la cierra al terminar.

    Yields:
        La conexión psycopg abierta.

    Raises:
        HTTPException: 503 si no se puede conectar o si la bbdd cae durante
            la petición (sin filtrar detalles internos al cliente).
    """
    try:
        conn = connect(get_settings())
    except psycopg.OperationalError:
        logger.exception("No se pudo conectar a la base de datos")
        raise HTTPException(503, "Base de datos no disponible") from None
    try:
        yield conn
    except psycopg.OperationalError:  # la bbdd cae a mitad de petición
        logger.exception("Base de datos caída durante la petición")
        raise HTTPException(503, "Base de datos no disponible") from None
    finally:
        conn.close()


def find_user(conn, username: str) -> dict | None:
    """Datos del usuario para login y reseteo, o None si no existe.

    `reset_hash` solo se devuelve si la contraseña pendiente no ha caducado: así el login no
    tiene que comprobar fechas.
    """
    row = conn.execute(
        "SELECT password_hash, email, CASE WHEN reset_expira > now() THEN reset_hash END, es_admin"
        " FROM usuarios WHERE username = %s",
        (username,),
    ).fetchone()
    return {"password_hash": row[0], "email": row[1], "reset_hash": row[2], "es_admin": row[3]} if row else None


def get_es_admin(conn, username: str) -> bool | None:
    """Si el usuario es administrador; None si ya no existe (la sesión apunta a un usuario borrado).

    Se consulta en cada petición protegida, en vez de guardarlo en la cookie, para que quitar el
    permiso en la bbdd surta efecto al momento.
    """
    row = conn.execute("SELECT es_admin FROM usuarios WHERE username = %s", (username,)).fetchone()
    return row[0] if row else None


def save_pending_password(conn, username: str, hashed: str) -> None:
    """Guarda la contraseña del reseteo como pendiente durante 1 hora. NO hace commit.

    Sin commit a propósito: el reseteo solo confirma si el correo se ha enviado (si no, rollback).
    """
    conn.execute(
        "UPDATE usuarios SET reset_hash = %s, reset_expira = now() + interval '1 hour' WHERE username = %s",
        (hashed, username),
    )


def promote_pending_password(conn, username: str) -> None:
    """La contraseña pendiente pasa a ser la del usuario (se ha entrado con ella)."""
    conn.execute(
        "UPDATE usuarios SET password_hash = reset_hash, reset_hash = NULL, reset_expira = NULL"
        " WHERE username = %s AND reset_hash IS NOT NULL",
        (username,),
    )
    conn.commit()


def discard_pending_password(conn, username: str) -> None:
    """Descarta la contraseña pendiente (se ha entrado con la de siempre)."""
    conn.execute("UPDATE usuarios SET reset_hash = NULL, reset_expira = NULL WHERE username = %s", (username,))
    conn.commit()


def mark_captcha_used(conn, signature: str, expires_at: int) -> bool:
    """Apunta un reto de captcha como usado. Devuelve False si ya lo estaba (reenvío).

    De paso borra los retos caducados: ya no se pueden reutilizar porque la firma caduca sola.
    """
    conn.execute("DELETE FROM captchas_usados WHERE expira < now()")
    inserted = conn.execute(
        "INSERT INTO captchas_usados (firma, expira) VALUES (%s, to_timestamp(%s))"
        " ON CONFLICT (firma) DO NOTHING RETURNING firma",
        (signature, expires_at),
    ).fetchone()
    conn.commit()
    return inserted is not None


def count_reset_attempts(conn, keys: list[str]) -> int:
    """Máximo de intentos de reseteo en la última hora entre las claves dadas (usuario, IP)."""
    row = conn.execute(
        "SELECT coalesce(max(n), 0) FROM (SELECT count(*) AS n FROM intentos_reset"
        " WHERE clave = ANY(%s) AND creado_en > now() - interval '1 hour' GROUP BY clave) t",
        (keys,),
    ).fetchone()
    return row[0]


def add_reset_attempt(conn, keys: list[str]) -> None:
    """Apunta un intento de reseteo para cada clave y borra los de hace más de un día."""
    conn.execute("DELETE FROM intentos_reset WHERE creado_en < now() - interval '1 day'")
    for key in keys:
        conn.execute("INSERT INTO intentos_reset (clave) VALUES (%s)", (key,))
    conn.commit()


# --- Roles (issue #5) ---

class NombreDuplicado(Exception):
    """Ya hay un rol con ese nombre (la columna roles.nombre es única)."""


def _rol(row) -> dict:
    return {"id": row[0], "nombre": row[1], "descripcion": row[2], "num_usuarios": row[3]}


def list_roles(conn) -> list[dict]:
    """Todos los roles por nombre, con cuántos usuarios tiene cada uno."""
    rows = conn.execute(
        "SELECT r.id, r.nombre, r.descripcion, count(ur.usuario_id) FROM roles r"
        " LEFT JOIN usuario_roles ur ON ur.rol_id = r.id GROUP BY r.id ORDER BY r.nombre"
    ).fetchall()
    return [_rol(r) for r in rows]


def create_role(conn, nombre: str, descripcion: str | None) -> dict:
    """Crea un rol y lo devuelve.

    Raises:
        NombreDuplicado: si ya existe uno con ese nombre.
    """
    try:
        row = conn.execute(
            "INSERT INTO roles (nombre, descripcion) VALUES (%s, %s) RETURNING id, nombre, descripcion, 0",
            (nombre, descripcion),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _rol(row)


def update_role(conn, rol_id: int, nombre: str, descripcion: str | None) -> dict | None:
    """Renombra o edita un rol y lo devuelve; None si no existe.

    Raises:
        NombreDuplicado: si el nombre nuevo ya lo tiene otro rol.
    """
    try:
        row = conn.execute(
            "UPDATE roles SET nombre = %s, descripcion = %s WHERE id = %s RETURNING id, nombre, descripcion,"
            " (SELECT count(*) FROM usuario_roles WHERE rol_id = roles.id)",
            (nombre, descripcion, rol_id),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _rol(row) if row else None


def delete_role(conn, rol_id: int) -> int | None:
    """Borra un rol si nadie lo tiene.

    Returns:
        None si el rol no existe; 0 si se ha borrado; N > 0 si lo tienen N usuarios y NO se borra
        (la bbdd también lo impediría: ON DELETE RESTRICT).
    """
    row = conn.execute(
        "SELECT (SELECT count(*) FROM usuario_roles WHERE rol_id = %s) FROM roles WHERE id = %s",
        (rol_id, rol_id),
    ).fetchone()
    if row is None:
        return None
    if row[0] == 0:
        conn.execute("DELETE FROM roles WHERE id = %s", (rol_id,))
        conn.commit()
    return row[0]


def role_users(conn, rol_id: int) -> list[dict] | None:
    """Usuarios que tienen el rol, por nombre; None si el rol no existe."""
    if conn.execute("SELECT 1 FROM roles WHERE id = %s", (rol_id,)).fetchone() is None:
        return None
    rows = conn.execute(
        "SELECT u.id, u.username, u.email FROM usuarios u JOIN usuario_roles ur ON ur.usuario_id = u.id"
        " WHERE ur.rol_id = %s ORDER BY u.username",
        (rol_id,),
    ).fetchall()
    return [{"id": r[0], "username": r[1], "email": r[2]} for r in rows]


# --- Proyectos (issue #7) ---
# NombreDuplicado (arriba) sirve también aquí: proyectos y documentos tienen índices únicos sobre
# lower(nombre), así que «Web» y «web» chocan y la bbdd lo garantiza sin carreras.

def _proyecto(row) -> dict:
    return {"id": row[0], "nombre": row[1], "tipo": row[2], "descripcion": row[3], "num_documentos": row[4]}


def list_projects(conn) -> list[dict]:
    """Todos los proyectos por nombre (sin distinguir mayúsculas), con cuántos documentos tiene cada uno."""
    rows = conn.execute(
        "SELECT p.id, p.nombre, p.tipo, p.descripcion, count(d.id) FROM proyectos p"
        " LEFT JOIN documentos d ON d.proyecto_id = p.id GROUP BY p.id ORDER BY lower(p.nombre)"
    ).fetchall()
    return [_proyecto(r) for r in rows]


def create_project(conn, nombre: str, tipo: str | None, descripcion: str | None) -> dict:
    """Crea un proyecto y lo devuelve.

    Raises:
        NombreDuplicado: si ya existe uno con ese nombre (sin distinguir mayúsculas).
    """
    try:
        row = conn.execute(
            "INSERT INTO proyectos (nombre, tipo, descripcion) VALUES (%s, %s, %s)"
            " RETURNING id, nombre, tipo, descripcion, 0",
            (nombre, tipo, descripcion),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _proyecto(row)


def get_project(conn, proyecto_id: int) -> dict | None:
    """Proyecto con la lista de sus documentos (id, nombre, tamaño en bytes); None si no existe.

    No carga el contenido de los documentos: el tamaño sale de octet_length en la propia bbdd.
    """
    row = conn.execute(
        "SELECT id, nombre, tipo, descripcion FROM proyectos WHERE id = %s", (proyecto_id,)
    ).fetchone()
    if row is None:
        return None
    docs = conn.execute(
        "SELECT id, nombre, octet_length(contenido) FROM documentos WHERE proyecto_id = %s ORDER BY lower(nombre)",
        (proyecto_id,),
    ).fetchall()
    return {"id": row[0], "nombre": row[1], "tipo": row[2], "descripcion": row[3],
            "documentos": [{"id": d[0], "nombre": d[1], "tamano": d[2]} for d in docs]}


def update_project(conn, proyecto_id: int, nombre: str, tipo: str | None, descripcion: str | None) -> dict | None:
    """Cambia nombre, tipo y descripción de un proyecto y lo devuelve; None si no existe.

    Raises:
        NombreDuplicado: si el nombre nuevo ya lo tiene otro proyecto (sin distinguir mayúsculas).
    """
    try:
        row = conn.execute(
            "UPDATE proyectos SET nombre = %s, tipo = %s, descripcion = %s WHERE id = %s"
            " RETURNING id, nombre, tipo, descripcion,"
            " (SELECT count(*) FROM documentos WHERE proyecto_id = proyectos.id)",
            (nombre, tipo, descripcion, proyecto_id),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return _proyecto(row) if row else None


def delete_project(conn, proyecto_id: int) -> bool:
    """Borra un proyecto y, por ON DELETE CASCADE, todos sus documentos. False si no existía."""
    borrado = conn.execute("DELETE FROM proyectos WHERE id = %s RETURNING id", (proyecto_id,)).fetchone()
    conn.commit()
    return borrado is not None


def add_document(conn, proyecto_id: int, nombre: str, contenido: bytes) -> dict | None:
    """Guarda un documento en un proyecto y lo devuelve (sin el contenido); None si el proyecto no existe.

    Raises:
        NombreDuplicado: si el proyecto ya tiene un documento con ese nombre (sin distinguir
            mayúsculas; la extensión forma parte del nombre).
    """
    try:
        # %b: el contenido viaja en binario; en texto psycopg lo pasaría a hexadecimal (el doble de bytes).
        row = conn.execute(
            "INSERT INTO documentos (proyecto_id, nombre, contenido)"
            " SELECT id, %s, %b FROM proyectos WHERE id = %s RETURNING id, nombre, octet_length(contenido)",
            (nombre, contenido, proyecto_id),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        raise NombreDuplicado from None
    conn.commit()
    return {"id": row[0], "nombre": row[1], "tamano": row[2]} if row else None


def get_document(conn, documento_id: int) -> dict | None:
    """Nombre y contenido de un documento; None si no existe."""
    # binary=True: sin él, Postgres manda el contenido en hexadecimal (el doble de bytes que decodificar).
    row = conn.execute("SELECT nombre, contenido FROM documentos WHERE id = %s", (documento_id,), binary=True).fetchone()
    return {"nombre": row[0], "contenido": bytes(row[1])} if row else None


def delete_document(conn, documento_id: int) -> bool:
    """Borra un documento. False si no existía."""
    borrado = conn.execute("DELETE FROM documentos WHERE id = %s RETURNING id", (documento_id,)).fetchone()
    conn.commit()
    return borrado is not None
