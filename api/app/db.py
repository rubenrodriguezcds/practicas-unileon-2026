import logging

import psycopg
from fastapi import HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_conn():
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
    row = conn.execute(
        "SELECT password_hash FROM usuarios WHERE username = %s", (username,)
    ).fetchone()
    return row[0] if row else None
