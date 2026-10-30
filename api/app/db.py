"""Acceso a la base de datos PostgreSQL.

Para qué: abre una conexión por petición HTTP y contiene las consultas SQL de la app.

Por qué existe: es el ÚNICO sitio que habla SQL. Los endpoints no saben nada de psycopg ni de
tablas; solo piden datos con funciones como `find_password_hash`. Si mañana se cambia a un ORM
(SQLAlchemy) o se añaden tablas, el cambio queda aquí.

Quién lo usa: routers/auth.py, a través de la dependencia de FastAPI `Depends(get_conn)`.

Notas:
  - Si Postgres no responde, se devuelve 503 «Base de datos no disponible» (y se deja en el log)
    en vez de un 500 genérico, para que el usuario sepa que el problema no es su contraseña.
  - La conexión se cierra siempre al acabar la petición, también si hay errores.
  - Dentro de Docker se conecta a `db:5432` (red interna), no al 1521 publicado al host.
"""

import logging

import psycopg
from fastapi import HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_conn():
    """Dependencia FastAPI: abre una conexión por petición y la cierra al terminar.

    Yields:
        La conexión psycopg abierta.

    Raises:
        HTTPException: 503 si no se puede conectar o si la bbdd cae durante
            la petición (sin filtrar detalles internos al cliente).
    """
    s = get_settings()
    try:
        conn = psycopg.connect(
            host=s.db_host, port=s.db_port, dbname=s.postgres_db,
            user=s.postgres_user, password=s.postgres_password, connect_timeout=3,
        )
    except psycopg.OperationalError:
        logger.exception("No se pudo conectar a la base de datos")
        raise HTTPException(503, "Base de datos no disponible")
    try:
        yield conn
    except psycopg.OperationalError:  # la bbdd cae a mitad de petición
        logger.exception("Base de datos caída durante la petición")
        raise HTTPException(503, "Base de datos no disponible")
    finally:
        conn.close()


def find_password_hash(conn, username: str) -> str | None:
    """Devuelve el hash de contraseña del usuario, o None si no existe."""
    row = conn.execute(
        "SELECT password_hash FROM usuarios WHERE username = %s", (username,)
    ).fetchone()
    return row[0] if row else None
