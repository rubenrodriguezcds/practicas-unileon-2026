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
