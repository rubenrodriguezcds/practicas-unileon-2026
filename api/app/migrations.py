"""Migraciones de la base de datos: cambios de esquema sobre una bbdd que ya existe.

Para qué: aplica al arrancar la API los ficheros `api/migrations/NNN_nombre.sql` que aún no se
hayan aplicado, en orden, y apunta cada uno en la tabla `migraciones_aplicadas`.

Por qué existe: los scripts de `db/init/` son el plano para construir la bbdd desde cero y
Postgres solo los ejecuta con el volumen vacío. Una migración es una reforma: añade una columna
o una tabla a una bbdd con datos sin tener que borrarla (`docker compose down -v`). Para cambiar
el esquema se añade un fichero nuevo; los ya aplicados no se editan.

Quién lo usa: main.py, al arrancar (lifespan). Los tests no arrancan el lifespan, así que nunca
tocan una bbdd real.

Notas: cada migración va en su propia transacción: si falla, no queda a medias y la API no
arranca (el error sale en `docker compose logs web`). Si el esquema crece mucho, cambiar a Alembic.
"""

import logging
from pathlib import Path

from app.config import Settings
from app.db import connect

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def apply_migrations(conn, admin_email: str | None, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica las migraciones pendientes y da email al admin si no tiene.

    Args:
        conn: conexión psycopg en modo autocommit (cada `transaction()` es una transacción real).
        admin_email: APP_ADMIN_EMAIL; si viene, se pone al usuario admin solo si su email está vacío.
        migrations_dir: carpeta de los .sql (los tests pasan una temporal).

    Returns:
        Nombres de las migraciones aplicadas en esta llamada.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS migraciones_aplicadas"
        " (nombre TEXT PRIMARY KEY, aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    done = {row[0] for row in conn.execute("SELECT nombre FROM migraciones_aplicadas").fetchall()}
    applied = []
    for f in sorted(migrations_dir.glob("*.sql")):
        if f.name in done:
            continue
        with conn.transaction():
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO migraciones_aplicadas (nombre) VALUES (%s)", (f.name,))
        logger.info("Migración aplicada: %s", f.name)
        applied.append(f.name)
    if admin_email:
        # El seed (db/init) no se vuelve a ejecutar en una bbdd existente: el email se pone aquí.
        conn.execute("UPDATE usuarios SET email = %s WHERE username = 'admin' AND email IS NULL", (admin_email,))
    return applied


def migrate(settings: Settings) -> None:
    """Conecta a la bbdd y aplica las migraciones pendientes (lo llama main.py al arrancar)."""
    with connect(settings, autocommit=True) as conn:
        apply_migrations(conn, settings.app_admin_email)
